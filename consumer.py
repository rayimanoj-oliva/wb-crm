# consumer.py
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
    content = task.get("content") or {}

    base = {
        "messaging_product": "whatsapp",
        "to": customer["wa_id"],
        "recipient_type": "individual"
    }

    if msg_type == "text":
        if not isinstance(content, str):
            raise ValueError("Text content must be a string")
        base.update({"type": "text", "text": content})

    elif msg_type == "template":
        template_name = content.get("name")
        if not template_name:
            raise ValueError("Template name is missing")

        language_code = content.get("language", {}).get("code", "en_US")
        components = content.get("components", [])
        if not isinstance(components, list):
            components = []

        base.update({
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components
            }
        })

    elif msg_type in ["image", "document"]:
        if not isinstance(content, dict):
            raise ValueError(f"{msg_type} content must be a dict with url or id")
        base.update({"type": msg_type, msg_type: content})

    else:
        raise ValueError(f"Unsupported message type: {msg_type}")

    return base


def send_whatsapp_request(payload, headers, retries=3):
    """Send request to WhatsApp Cloud API with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                return "success", res.text
            else:
                print(f"⚠️ Attempt {attempt}: API responded {res.status_code} - {res.text}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Attempt {attempt}: Network error: {e}")
        time.sleep(2 ** attempt)  # exponential backoff
    return "failure", None


def callback(ch, method, properties, body):
    db: Session = next(get_db())
    task = json.loads(body)
    customer = task["customer"]
    job_id = task["job_id"]
    campaign_id = task["campaign_id"]

    start_time = time.time()

    try:
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise Exception("WhatsApp token not available")

        headers = {"Authorization": f"Bearer {token_obj.token}", "Content-Type": "application/json"}
        payload = build_payload(task, customer)

        print(f"📤 Sending payload: {json.dumps(payload, indent=2)}")
        status, response_text = send_whatsapp_request(payload, headers)
        print(f"📩 Response: {response_text}")

    except Exception as e:
        print(f"❌ Error sending to {customer['wa_id']}: {e}")
        status = "failure"

    # Ensure JobStatus exists
    job_status = db.query(JobStatus).filter_by(job_id=job_id, customer_id=customer["id"]).first()
    if not job_status:
        job_status = JobStatus(job_id=job_id, customer_id=customer["id"], status=status)
        db.add(job_status)
    else:
        job_status.status = status

    # Update job and campaign metadata
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
