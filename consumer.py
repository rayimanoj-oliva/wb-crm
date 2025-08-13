import time
from datetime import datetime
import pika
import json
import requests
from sqlalchemy.orm import Session
from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import JobStatus, Campaign, Job
from services import whatsapp_service
from utils.json_placeholder import fill_placeholders


def build_payload(task, customer):
    """Build WhatsApp API payload depending on message type."""
    msg_type = task["type"]
    content = task["content"]

    base = {
        "messaging_product": "whatsapp",
        "to": customer["wa_id"],
        "recipient_type": "individual"
    }

    # For text messages
    if msg_type == "text":
        base.update({
            "type": "text",
            "text": content
        })

    # For template messages
    elif msg_type == "template":
        # Ensure placeholders are filled before sending
        template_name = content.get("name")
        language_code = content.get("language", {}).get("code", "en_US")
        components = content.get("components", [])

        base.update({
            "type": "template",
            "template": {
                "name": template_name,
                "language": { "code": language_code },
                "components": components
            }
        })

    # For image / document messages
    elif msg_type in ["image", "document"]:
        base.update({
            "type": msg_type,
            msg_type: content
        })

    else:
        raise ValueError(f"Unsupported message type: {msg_type}")

    return base


def callback(ch, method, properties, body):
    db: Session = next(get_db())
    task = json.loads(body)
    customer = task["customer"]
    job_id = task["job_id"]
    campaign_id = task["campaign_id"]

    start_time = time.time()

    try:
        # Get latest token
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise Exception("Token not available")

        token = token_obj.token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Build correct payload depending on type
        payload = build_payload(task, customer)

        # Send request to WhatsApp
        res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        print(f"📤 Payload Sent: {json.dumps(payload, indent=2)}")
        print(f"📩 Response ({res.status_code}): {res.text}")

        status = "success" if res.status_code == 200 else "failure"

    except Exception as e:
        print(f"❌ Error sending to {customer['wa_id']}: {e}")
        status = "failure"

    # Update status in DB
    job_status = db.query(JobStatus).filter_by(
        job_id=job_id,
        customer_id=customer["id"]
    ).first()

    if job_status:
        job_status.status = status

    # Update job and campaign last trigger time
    job = db.query(Job).filter_by(id=job_id).first()
    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if job:
        job.last_triggered_time = datetime.utcnow()
    if campaign:
        campaign.last_job_id = job_id

    db.commit()

    duration = round(time.time() - start_time, 2)
    print(f"[{status.upper()}] {customer['wa_id']} - {duration}s")
    ch.basic_ack(delivery_tag=method.delivery_tag)


def start_worker():
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue="campaign_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="campaign_queue", on_message_callback=callback)
    print("🚀 Worker started. Waiting for messages...")
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()
