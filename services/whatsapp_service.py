import json
import copy

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
    base_components = template_content.get("components", [])
    recipient_params = recipient.get('params') or {}

    def replace_component(components_list, comp_type, new_component):
        filtered = [c for c in components_list if c.get("type", "").lower() != comp_type.lower()]
        if new_component:
            filtered.append(new_component)
        return filtered

    # Start with base components if available, otherwise empty list
    components = copy.deepcopy(base_components) if base_components else []

    body_params = recipient_params.get("body_params")
    header_text_params = recipient_params.get("header_text_params")
    header_media_id = recipient_params.get("header_media_id")

    # Only create body component if we have actual body params (non-empty list)
    if body_params is not None and len(body_params) > 0:
        # Filter out None/empty values and ensure all are strings
        valid_params = [str(v).strip() if v is not None else "" for v in body_params]
        if any(valid_params):  # Only add if at least one param has a value
            body_component = {
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in valid_params]
            }
            components = replace_component(components, "body", body_component)

    # Handle header - prioritize media_id over text params
    if header_media_id and str(header_media_id).strip():
        header_component = {
            "type": "header",
            "parameters": [
                {"type": "image", "image": {"id": str(header_media_id).strip()}}
            ]
        }
        components = replace_component(components, "header", header_component)
    elif header_text_params is not None and len(header_text_params) > 0:
        # Filter out None/empty values
        valid_params = [str(v).strip() if v is not None else "" for v in header_text_params]
        if any(valid_params):  # Only add if at least one param has a value
            header_component = {
                "type": "header",
                "parameters": [{"type": "text", "text": v} for v in valid_params]
            }
            components = replace_component(components, "header", header_component)

    # Fallback to placeholder replacement if no structured params provided but recipient_params exist
    if not body_params and not header_text_params and not header_media_id and recipient_params:
        mock_customer = {
            'wa_id': recipient['phone_number'],
            'name': recipient.get('name', ''),
            **recipient_params
        }
        if components:
            components = fill_placeholders(components, mock_customer)

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient['phone_number'],
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components if components else []  # Ensure components is always a list
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