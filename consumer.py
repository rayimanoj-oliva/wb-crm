import time
from datetime import datetime
import json, requests, pika
from sqlalchemy.orm import Session
from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import JobStatus, Campaign, Job
from services import whatsapp_service


def callback(ch, method, properties, body):
    print(f"[CONSUMER] Received message from queue")
    db: Session = next(get_db())

    try:
        task = json.loads(body)
    except Exception as e:
        print(f"[CONSUMER ERROR] Failed to parse message body: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = task.get("job_id")
    campaign_id = task.get("campaign_id")
    target_type = task.get("target_type")      # "recipient" | "customer"
    target_id = task.get("target_id")

    print(f"[CONSUMER] Processing Job {job_id}, Campaign {campaign_id}, Target {target_type}:{target_id}")

    start_time = time.time()
    status = "failure"

    try:
        from uuid import UUID
        job_id_uuid = UUID(job_id) if isinstance(job_id, str) else job_id
        campaign_id_uuid = UUID(campaign_id) if isinstance(campaign_id, str) else campaign_id
        
        job = db.query(Job).filter_by(id=job_id_uuid).first()
        campaign = db.query(Campaign).filter_by(id=campaign_id_uuid).first()

        if not campaign:
            print(f"[CONSUMER ERROR] Campaign {campaign_id} not found")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 1) Load target from DB
        from uuid import UUID
        try:
            target_id_uuid = UUID(target_id) if isinstance(target_id, str) else target_id
        except:
            print(f"[CONSUMER ERROR] Invalid target_id format: {target_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        if target_type == "recipient":
            from models.models import CampaignRecipient
            target = db.query(CampaignRecipient).filter_by(id=target_id_uuid).first()
            if not target:
                print(f"[CONSUMER ERROR] Recipient {target_id} not found")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            wa_id = target.phone_number
        else:
            from models.models import Customer
            target = db.query(Customer).filter_by(id=target_id_uuid).first()
            if not target:
                print(f"[CONSUMER ERROR] Customer {target_id} not found")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            wa_id = target.wa_id

        if not wa_id:
            print(f"[CONSUMER ERROR] No wa_id/phone for target {target_type}:{target_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # 2) Get token
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise Exception("Token not available")

        token = token_obj.token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 3) Build payload (only place with branching)
        if campaign.type == "template":
            if target_type == "recipient":
                # Convert CampaignRecipient object to dict format expected by build_template_payload_for_recipient
                # Ensure params is a proper dict (JSONB columns might need conversion)
                recipient_params = target.params if target.params else {}
                if not isinstance(recipient_params, dict):
                    # If params is stored as string or other format, try to parse it
                    try:
                        if isinstance(recipient_params, str):
                            recipient_params = json.loads(recipient_params)
                        else:
                            recipient_params = dict(recipient_params) if recipient_params else {}
                    except:
                        recipient_params = {}
                
                recipient_dict = {
                    "phone_number": target.phone_number,
                    "name": target.name,
                    "params": recipient_params
                }
                payload = whatsapp_service.build_template_payload_for_recipient(
                    recipient_dict, campaign.content
                )
            else:
                # Convert Customer object to dict format expected by build_template_payload
                customer_dict = {
                    "wa_id": target.wa_id,
                    "name": target.name or ""
                }
                payload = whatsapp_service.build_template_payload(
                    customer_dict, campaign.content
                )
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "recipient_type": "individual",
                "type": campaign.type,
                campaign.type: campaign.content,
            }

        # 4) Send request
        res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        status = "success" if res.status_code == 200 else "failure"

        if status == "failure":
            try:
                error_json = res.json()
                error_msg = error_json.get("error", {}).get("message", res.text)
                error_code = error_json.get("error", {}).get("code", res.status_code)
                # print(f"[FAILURE] Failed to send message to {wa_id}. Code: {error_code}, Message: {error_msg}")
                # print(f"[FAILURE] Payload sent: {json.dumps(payload, indent=2)}")
            except:
                print(f"[FAILURE] Failed to send message to {wa_id}. Status: {res.status_code}, Response: {res.text[:500]}")
                # print(f"[FAILURE] Payload sent: {json.dumps(payload, indent=2)}")

    except Exception as e:
        import traceback
        print(f"[EXCEPTION] Error sending to {target_type}:{target_id} - {str(e)}")
        print(traceback.format_exc())
        if 'payload' in locals():
            print(f"[EXCEPTION] Payload that caused error: {json.dumps(payload, indent=2)}")

    # 5) Update DB statuses
    duration = round(time.time() - start_time, 2)

    if target_type == "customer":
        from uuid import UUID
        try:
            customer_id_uuid = UUID(target_id) if isinstance(target_id, str) else target_id
            job_id_uuid = UUID(job_id) if isinstance(job_id, str) else job_id
            job_status = db.query(JobStatus).filter_by(job_id=job_id_uuid, customer_id=customer_id_uuid).first()
            if job_status:
                job_status.status = status
        except:
            pass

    if job:
        job.last_triggered_time = datetime.utcnow()
    if campaign:
        from uuid import UUID
        job_id_uuid = UUID(job_id) if isinstance(job_id, str) else job_id
        campaign.last_job_id = job_id_uuid

    if target_type == "recipient":
        from models.models import CampaignRecipient
        from uuid import UUID
        try:
            recipient_id_uuid = UUID(target_id) if isinstance(target_id, str) else target_id
            recipient = db.query(CampaignRecipient).filter_by(id=recipient_id_uuid).first()
            if recipient:
                recipient.status = "SENT" if status == "success" else "FAILED"
        except:
            pass

    db.commit()
    print(f"[{status.upper()}] {target_type}:{wa_id} - {duration}s")

    ch.basic_ack(delivery_tag=method.delivery_tag)


def start_worker():
    print("🚀 Worker started — listening for messages...")
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue="campaign_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="campaign_queue", on_message_callback=callback)
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()