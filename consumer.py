import time
from datetime import datetime
import json, requests, pika
from sqlalchemy.orm import Session
from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import JobStatus, Campaign, Job
from services import whatsapp_service


def build_template_payload(customer, content: dict):
    """
    Build WhatsApp template payload.
    content must include at least:
    {
      "template_name": "welcome_message",
      "language": "en_US"
    }

    Personalization:
    - First parameter = customer's name (fallback = wa_id)
    - Additional parameters can be provided in content["parameters"]
    """
    parameters = []

    # Insert customer's name as first parameter (fallback = wa_id)
    if customer.get("name"):
        parameters.append({"type": "text", "text": customer["name"]})
    else:
        parameters.append({"type": "text", "text": customer["wa_id"]})

    # Add any extra parameters from campaign.content
    extra_params = content.get("parameters", [])
    for p in extra_params:
        parameters.append({"type": "text", "text": str(p)})

    components = []
    if parameters:
        components.append({
            "type": "body",
            "parameters": parameters
        })

    return {
        "messaging_product": "whatsapp",
        "to": customer["wa_id"],
        "type": "template",
        "template": {
            "name": content["template_name"],
            "language": {"code": content.get("language", "en_US")},
            "components": components
        }
    }


def callback(ch, method, properties, body):
    """
    RabbitMQ worker callback to process each task.
    Supports both generic and template messages.
    """
    db: Session = next(get_db())
    task = json.loads(body)
    customer = task['customer']
    job_id = task['job_id']
    campaign_id = task['campaign_id']

    start_time = time.time()  # Start timing

    try:
        # Get latest WhatsApp token
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise Exception("Token not available")
        token = token_obj.token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 🔹 Build payload depending on type
        if task['type'] == "template":
            payload = build_template_payload(customer, task['content'])
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": customer['wa_id'],
                "recipient_type": "individual",
                "type": task['type'],
                task['type']: task['content']
            }

        print("📤 Sending payload:", json.dumps(payload, indent=2))

        # Send WhatsApp message
        res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        result = res.json()

        if "error" in result:
            print(f"❌ Error sending to {customer['wa_id']}: {result['error']}")
            status = "failure"
        else:
            print(f"✅ Message sent to {customer['wa_id']}: {result}")
            status = "success"

    except Exception as e:
        print(f"⚠️ Exception while sending to {customer['wa_id']}: {e}")
        status = "failure"

    end_time = time.time()
    duration = round(end_time - start_time, 2)

    # Update JobStatus
    job_status = db.query(JobStatus).filter_by(job_id=job_id, customer_id=customer['id']).first()
    if job_status:
        job_status.status = status

    # Update Job and Campaign
    job = db.query(Job).filter_by(id=job_id).first()
    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if job:
        job.last_triggered_time = datetime.utcnow()
        if campaign:
            campaign.last_job_id = job_id

    db.commit()
    print(f"[{status.upper()}] {customer['wa_id']} - {duration}s")

    # Acknowledge message in RabbitMQ
    ch.basic_ack(delivery_tag=method.delivery_tag)


def start_worker():
    """Start RabbitMQ worker to consume messages from 'campaign_queue'."""
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue="campaign_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="campaign_queue", on_message_callback=callback)
    print("🚀 Worker started. Waiting for messages...")
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()
