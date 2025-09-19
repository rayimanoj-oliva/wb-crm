import json

import pika
from sqlalchemy.orm import Session
from models.models import WhatsAppToken
from schemas.whatsapp_token_schema import WhatsAppTokenCreate
from utils.json_placeholder import fill_placeholders

def create_whatsapp_token(db: Session, token_data: WhatsAppTokenCreate):
    token_entry = WhatsAppToken(token=token_data.token)
    db.add(token_entry)
    db.commit()
    db.refresh(token_entry)
    return token_entry

def get_latest_token(db: Session):
    return db.query(WhatsAppToken).order_by(WhatsAppToken.created_at.desc()).first()

def build_template_payload(customer: dict, template_content: dict):

    template_name = template_content.get("name")
    language_code = template_content.get("language", "en_US")
    components = template_content.get("components", [])

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

def build_template_payload_for_recipient(recipient: dict, template_content: dict):
    """
    Build template payload for Excel-uploaded recipients.
    Uses recipient's custom params instead of customer data.
    """
    template_name = template_content.get("name")
    language_code = template_content.get("language", "en_US")
    components = template_content.get("components", [])

    # For recipients, we need to replace placeholders with their custom params
    if components and recipient.get('params'):
        # Create a mock customer dict with recipient's params for placeholder replacement
        mock_customer = {
            'wa_id': recipient['phone_number'],
            'name': recipient.get('name', ''),
            **recipient.get('params', {})  # Include custom params
        }
        components = fill_placeholders(components, mock_customer)

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient['phone_number'],
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components
        }
    }
    return payload

def enqueue_template_message(to: str, template_name: str, parameters: list):
    payload = {
        "to": to,
        "template_name": template_name,
        "parameters": [p.model_dump() for p in parameters]
    }
    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    ch = conn.channel()
    ch.queue_declare(queue="whatsapp_campaign", durable=True)
    ch.basic_publish(
        exchange='',
        routing_key='whatsapp_campaign',
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    conn.close()