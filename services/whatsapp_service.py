import json
import copy
import logging

import pika
from sqlalchemy.orm import Session
from models.models import WhatsAppToken
from schemas.whatsapp_token_schema import WhatsAppTokenCreate
from utils.json_placeholder import fill_placeholders

# Configure logging
logger = logging.getLogger(__name__)

# Correct queue name - must match consumer.py
CAMPAIGN_QUEUE_NAME = "campaign_queue"


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

    # Get params from recipient first
    body_params = recipient_params.get("body_params")
    header_text_params = recipient_params.get("header_text_params")
    header_media_id = recipient_params.get("header_media_id")
    
    # IMPORTANT: Do NOT start with base_components as they contain raw template definition
    # (text, format, example fields) which are not valid for WhatsApp API.
    # Instead, start with empty list and only add properly formatted API components.
    components = []
    
    # Extract button index from template metadata if not provided in recipient params
    # This ensures we use the correct button index from the template definition
    template_button_index = None
    for comp in base_components:
        if comp.get("type", "").upper() == "BUTTONS":
            buttons = comp.get("buttons", [])
            for button in buttons:
                if button.get("type", "").upper() == "URL":
                    template_button_index = str(button.get("index", "0"))
                    break
            if template_button_index:
                break
    
    # Optional button parameters (for template URL buttons, etc.)
    button_params = recipient_params.get("button_params")
    # Use recipient's button_index if provided, otherwise use template's button_index, fallback to "0"
    button_index = recipient_params.get("button_index") or template_button_index or "0"
    button_sub_type = recipient_params.get("button_sub_type", "url")

    # Use logger instead of print for debugging
    logger.debug(f"Building template payload for recipient: {recipient.get('phone_number')}")
    logger.debug(f"Body params: {body_params}, Button params: {button_params}")

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
            logger.debug(f"Created body component with {len(valid_params)} params")

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

    # Handle template button parameters (e.g. URL buttons with dynamic param)
    # This builds a WhatsApp "button" component similar to your working Postman payload:
    # {
    #   "type": "button",
    #   "sub_type": "url",
    #   "index": "0",  # Button indices are 0-indexed (0, 1, 2, etc.)
    #   "parameters": [{ "type": "text", "text": "3WBCRqn" }]
    # }
    if button_params is not None and len(button_params) > 0:
        valid_params = [str(v).strip() if v is not None else "" for v in button_params]
        if any(valid_params):
            button_component = {
                "type": "button",
                "sub_type": str(button_sub_type or "url"),
                "index": str(button_index),  # button_index is already set correctly above (from recipient, template, or "0")
                "parameters": [{"type": "text", "text": v} for v in valid_params]
            }
            components = replace_component(components, "button", button_component)
            logger.debug(f"Created button component with index={button_index}, {len(valid_params)} params")

    # Fallback to placeholder replacement if no structured params provided but recipient_params exist
    if not body_params and not header_text_params and not header_media_id and not button_params and recipient_params:
        mock_customer = {
            'wa_id': recipient['phone_number'],
            'name': recipient.get('name', ''),
            **recipient_params
        }
        if components:
            components = fill_placeholders(components, mock_customer)

    # Ensure we have at least the body component if body_params were provided
    # WhatsApp requires components array even if empty, but we should have body component if params exist
    if not components and body_params and len(body_params) > 0:
        # This shouldn't happen, but as a safety check, build body component
        valid_params = [str(v).strip() if v is not None else "" for v in body_params]
        if any(valid_params):
            components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in valid_params]
            }]
            logger.debug("Rebuilt body component as fallback")

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
    logger.debug(f"Built template payload for {recipient['phone_number']}")
    return payload


def enqueue_template_message(to: str, template_name: str, parameters: list):
    """
    Enqueue a template message to RabbitMQ.
    FIXED: Now uses correct queue name 'campaign_queue' to match consumer.
    """
    payload = {
        "to": to,
        "template_name": template_name,
        "parameters": [p.model_dump() for p in parameters]
    }
    try:
        conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        ch = conn.channel()
        # FIXED: Use correct queue name that consumer listens to
        ch.queue_declare(queue=CAMPAIGN_QUEUE_NAME, durable=True)
        ch.basic_publish(
            exchange='',
            routing_key=CAMPAIGN_QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        conn.close()
        logger.info(f"Enqueued template message to {to}")
    except Exception as e:
        logger.error(f"Failed to enqueue template message: {e}")
        raise