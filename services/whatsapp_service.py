import json
import pika
from sqlalchemy.orm import Session
from models.models import WhatsAppToken
from utils.json_placeholder import fill_placeholders


def get_latest_token(db: Session):
    return db.query(WhatsAppToken).order_by(WhatsAppToken.created_at.desc()).first()


def build_template_payload(customer: dict, content: dict):
    """
    Build WhatsApp Cloud API payload for template messages.
    content = {
        "name": "welcome_msg",
        "language": "en_US",
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "John Doe"}
                ]
            }
        ]
    }
    """
    template_name = content.get("name")
    language_code = content.get("language", "en_US")
    components = content.get("components", [])

    # Replace placeholders dynamically
    if components:
        components = fill_placeholders(components, customer)

    payload = {
        "messaging_product": "whatsapp",
        "to": customer['wa_id'],
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components
        }
    }
    return payload


def enqueue_template_message(to: str, template_name: str, parameters: list, language="en_US"):
    """
    Enqueue a template message for campaign worker.
    `parameters` = list of text strings corresponding to placeholders in template
    """
    components = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in parameters]
        }
    ]

    task_payload = {
        "customer": {"wa_id": to},
        "type": "template",
        "content": {
            "name": template_name,
            "language": language,
            "components": components
        }
    }

    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    ch = conn.channel()
    ch.queue_declare(queue="campaign_queue", durable=True)
    ch.basic_publish(
        exchange='',
        routing_key='campaign_queue',
        body=json.dumps(task_payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    conn.close()
