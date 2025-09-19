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
    db: Session = next(get_db())
    task = json.loads(body)
    job_id = task['job_id']
    campaign_id = task['campaign_id']

    start_time = time.time()  # Start timing

    # Determine if this is a customer or recipient task
    is_recipient_task = 'recipient' in task
    target_info = task['recipient'] if is_recipient_task else task['customer']
    target_wa_id = target_info.get('phone_number') if is_recipient_task else target_info['wa_id']

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
                payload = whatsapp_service.build_template_payload_for_recipient(target_info, task['content'])
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
            print(f"Failed to send message to {target_wa_id}. Response: {res.text}")

    except Exception as e:
        print(f"Error sending to {target_wa_id}: {e}")
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
        recipient = db.query(CampaignRecipient).filter_by(id=target_info['id']).first()
        if recipient:
            recipient.status = "SENT" if status == "success" else "FAILED"

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