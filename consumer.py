import time
from datetime import datetime
import json, requests, pika
from sqlalchemy.orm import Session
from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import JobStatus, Campaign, Job
from services import whatsapp_service


def callback(ch, method, properties, body):
    """
    RabbitMQ worker callback to process each task.
    Supports both generic and template messages.
    Handles both CRM customers and Excel-uploaded recipients.
    """
    print(f"[CONSUMER] Received message from queue")
    db: Session = next(get_db())
    try:
        task = json.loads(body)
    except Exception as e:
        print(f"[CONSUMER ERROR] Failed to parse message body: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return
    
    job_id = task.get('job_id')
    campaign_id = task.get('campaign_id')
    print(f"[CONSUMER] Processing task - Job ID: {job_id}, Campaign ID: {campaign_id}")

    start_time = time.time()  # Start timing

    # Determine if this is a customer or recipient task
    is_recipient_task = 'recipient' in task
    print(f"[CONSUMER] Task type: {'recipient' if is_recipient_task else 'customer'}")
    
    if is_recipient_task:
        target_info = task.get('recipient', {})
        target_wa_id = target_info.get('phone_number')
    else:
        target_info = task.get('customer', {})
        target_wa_id = target_info.get('wa_id')
    
    if not target_wa_id:
        print(f"[CONSUMER ERROR] No phone number/wa_id found in task: {json.dumps(task, indent=2, default=str)}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        # Get latest WhatsApp token
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise Exception("Token not available")
        token = token_obj.token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 🔹 Build payload depending on type
        if task['type'] == "template":
            if is_recipient_task:
                # For Excel recipients, build template payload with their params
                print(f"[DEBUG consumer] Building payload for recipient task")
                print(f"[DEBUG consumer] Target info: {json.dumps(target_info, indent=2, default=str)}")
                print(f"[DEBUG consumer] Task content: {json.dumps(task['content'], indent=2, default=str)}")
                payload = whatsapp_service.build_template_payload_for_recipient(target_info, task['content'])
                print(f"[DEBUG consumer] Built payload: {json.dumps(payload, indent=2, default=str)}")
            else:
                payload = whatsapp_service.build_template_payload(target_info, task['content'])
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": target_wa_id,
                "recipient_type": "individual",
                "type": task['type'],
                task['type']: task['content']
            }

        # Send WhatsApp message
        res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        status = "success" if res.status_code == 200 else "failure"

        if status == "failure":
            try:
                error_json = res.json()
                error_msg = error_json.get("error", {}).get("message", res.text)
                error_code = error_json.get("error", {}).get("code", res.status_code)
                print(f"[FAILURE] Failed to send message to {target_wa_id}. Code: {error_code}, Message: {error_msg}")
                print(f"[FAILURE] Payload sent: {json.dumps(payload, indent=2)}")
            except:
                print(f"[FAILURE] Failed to send message to {target_wa_id}. Status: {res.status_code}, Response: {res.text[:500]}")
                print(f"[FAILURE] Payload sent: {json.dumps(payload, indent=2)}")

    except Exception as e:
        import traceback
        print(f"[EXCEPTION] Error sending to {target_wa_id}: {str(e)}")
        print(f"[EXCEPTION] Traceback: {traceback.format_exc()}")
        if 'payload' in locals():
            print(f"[EXCEPTION] Payload that caused error: {json.dumps(payload, indent=2)}")
        status = "failure"

    end_time = time.time()
    duration = round(end_time - start_time, 2)

    # Update JobStatus - only for customer tasks (recipients don't have JobStatus entries)
    if not is_recipient_task:
        job_status = db.query(JobStatus).filter_by(job_id=job_id, customer_id=target_info['id']).first()
        if job_status:
            job_status.status = status

    # Update Job and Campaign
    job = db.query(Job).filter_by(id=job_id).first()
    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if job:
        job.last_triggered_time = datetime.utcnow()
        if campaign:
            campaign.last_job_id = job_id

    # Update recipient status if it's a recipient task
    if is_recipient_task:
        from models.models import CampaignRecipient
        from uuid import UUID
        recipient_id = target_info.get('id')
        if recipient_id:
            try:
                # Convert string UUID to UUID object if needed
                if isinstance(recipient_id, str):
                    recipient_id = UUID(recipient_id)
                recipient = db.query(CampaignRecipient).filter_by(id=recipient_id).first()
                if recipient:
                    recipient.status = "SENT" if status == "success" else "FAILED"
                    print(f"[CONSUMER] Updated recipient {recipient_id} status to: {recipient.status}")
                else:
                    print(f"[CONSUMER WARNING] Recipient with ID {recipient_id} not found in database")
            except Exception as e:
                print(f"[CONSUMER ERROR] Failed to update recipient status: {str(e)}")
                import traceback
                print(f"[CONSUMER ERROR] Traceback: {traceback.format_exc()}")
        else:
            print(f"[CONSUMER WARNING] No recipient ID found in target_info")

    db.commit()
    task_type = "recipient" if is_recipient_task else "customer"
    print(f"[{status.upper()}] {task_type}:{target_wa_id} - {duration}s")

    # Acknowledge message in RabbitMQ
    ch.basic_ack(delivery_tag=method.delivery_tag)


def start_worker():
    """Start RabbitMQ worker to consume messages from 'campaign_queue'."""
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue="campaign_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="campaign_queue", on_message_callback=callback)
    print("Worker started. Waiting for messages...")
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()