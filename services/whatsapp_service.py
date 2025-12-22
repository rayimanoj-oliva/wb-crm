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

    # Convert Excel format (body_var_1, body_var_2, etc.) to body_params list if needed
    # Excel uploads store columns as body_var_1, body_var_2, body_var_3, etc.
    # But the code expects body_params as a list
    if "body_params" not in recipient_params or recipient_params.get("body_params") is None:
        # Check for Excel format: body_var_1, body_var_2, etc.
        body_var_keys = sorted([k for k in recipient_params.keys() if k.startswith("body_var_")])
        if body_var_keys:
            # Extract numeric suffix and sort by it
            def get_var_index(key):
                try:
                    return int(key.replace("body_var_", ""))
                except:
                    return 999
            body_var_keys = sorted(body_var_keys, key=get_var_index)
            # Include ALL body_var values, even if empty, to match template's expected parameter count
            body_params = []
            for k in body_var_keys:
                val = recipient_params.get(k)
                if val is None:
                    body_params.append("")
                else:
                    body_params.append(str(val).strip())
            # Only set to None if we found no body_var keys at all
            if not body_params:
                body_params = None
        else:
            body_params = None
    else:
        body_params = recipient_params.get("body_params")
        # Convert to list if it's a string (shouldn't happen, but safety check)
        if isinstance(body_params, str):
            body_params = [body_params.strip()] if body_params.strip() else []
        elif not isinstance(body_params, list):
            body_params = [str(body_params).strip()] if body_params is not None else None
    
    # Convert Excel format (header_var_1, header_var_2, etc.) to header_text_params list if needed
    if "header_text_params" not in recipient_params or recipient_params.get("header_text_params") is None:
        # Check for Excel format: header_var_1, header_var_2, etc.
        header_var_keys = sorted([k for k in recipient_params.keys() if k.startswith("header_var_")])
        if header_var_keys:
            def get_var_index(key):
                try:
                    return int(key.replace("header_var_", ""))
                except:
                    return 999
            header_var_keys = sorted(header_var_keys, key=get_var_index)
            # Include ALL header_var values, even if empty, to match template's expected parameter count
            header_text_params = []
            for k in header_var_keys:
                val = recipient_params.get(k)
                if val is None:
                    header_text_params.append("")
                else:
                    header_text_params.append(str(val).strip())
            # Only set to None if we found no header_var keys at all
            if not header_text_params:
                header_text_params = None
        else:
            header_text_params = None
    else:
        header_text_params = recipient_params.get("header_text_params")
        # Convert to list if it's a string
        if isinstance(header_text_params, str):
            header_text_params = [header_text_params.strip()] if header_text_params.strip() else []
        elif not isinstance(header_text_params, list):
            header_text_params = [str(header_text_params).strip()] if header_text_params is not None else None
    
    header_media_id = recipient_params.get("header_media_id")

    # IMPORTANT: Do NOT start with base_components as they contain raw template definition
    # (text, format, example fields) which are not valid for WhatsApp API.
    # Instead, start with empty list and only add properly formatted API components.
    components = []

    # Extract button metadata from template definition
    # - template_button_index: default button index from template
    # - button_requires_param: True if URL contains a {{placeholder}} and therefore
    #   requires a parameter according to WhatsApp
    template_button_index: Optional[str] = None
    button_requires_param: bool = False
    for comp in base_components:
        if comp.get("type", "").upper() == "BUTTONS":
            buttons = comp.get("buttons", [])
            for button in buttons:
                if button.get("type", "").upper() == "URL":
                    template_button_index = str(button.get("index", "0"))
                    url = button.get("url", "") or ""
                    # If URL has a placeholder, WhatsApp expects a parameter
                    if "{{" in url and "}}" in url:
                        button_requires_param = True
                    break
            if template_button_index is not None:
                break
    
    # Optional button parameters (for template URL buttons, etc.)
    # Handle both "button_params" (plural) and "button_param_1" (singular from Excel template)
    button_params_raw = recipient_params.get("button_params")
    if button_params_raw is None:
        # Check for Excel format: button_param_1, button_param_2, etc.
        button_param_keys = sorted([k for k in recipient_params.keys() if k.startswith("button_param_")])
        if button_param_keys:
            def get_param_index(key):
                try:
                    return int(key.replace("button_param_", ""))
                except:
                    return 999
            button_param_keys = sorted(button_param_keys, key=get_param_index)
            button_params_raw = [str(recipient_params[k]).strip() for k in button_param_keys if recipient_params.get(k) is not None and str(recipient_params[k]).strip()]
            if not button_params_raw:
                button_params_raw = None
    
    # Convert button_params to list if it's a string (from Excel upload)
    # Excel stores it as a string like "5123|PB56789" or comma-separated values
    if button_params_raw is not None:
        if isinstance(button_params_raw, str):
            # If string contains commas, split by comma; otherwise treat as single value
            if "," in button_params_raw:
                button_params = [p.strip() for p in button_params_raw.split(",") if p.strip()]
            else:
                stripped = button_params_raw.strip()
                # Handle "none", "null", "nan" strings
                if stripped.lower() in ('none', 'null', 'nan', ''):
                    button_params = []
                else:
                    button_params = [stripped]
        elif isinstance(button_params_raw, list):
            # Filter out None/null/nan values from list
            button_params = []
            for item in button_params_raw:
                if item is None:
                    continue
                item_str = str(item).strip()
                if item_str.lower() not in ('none', 'null', 'nan', ''):
                    button_params.append(item_str)
        else:
            # Convert other types to string and wrap in list
            item_str = str(button_params_raw).strip()
            if item_str.lower() in ('none', 'null', 'nan', ''):
                button_params = []
            else:
                button_params = [item_str]
    else:
        button_params = None
    
    # Use recipient's button_index if provided, otherwise use template's button_index, fallback to "0"
    button_index = recipient_params.get("button_index") or template_button_index or "0"
    button_sub_type = recipient_params.get("button_sub_type", "url")

    # Use logger instead of print for debugging
    logger.debug(f"Building template payload for recipient: {recipient.get('phone_number')}")
    logger.debug(f"Raw recipient_params keys: {list(recipient_params.keys())}")
    logger.debug(f"Body params: {body_params} (type: {type(body_params)})")
    logger.debug(f"Header text params: {header_text_params} (type: {type(header_text_params)})")
    logger.debug(f"Button params: {button_params} (type: {type(button_params_raw)})")
    logger.debug(f"Button index: {button_index}")

    # Only create body component if we have actual body params (non-empty list)
    if body_params is not None and len(body_params) > 0:
        # Filter out None/empty values and ensure all are strings
        # IMPORTANT: Keep empty strings if they exist, as template might require all parameters
        valid_params = []
        for v in body_params:
            if v is None:
                valid_params.append("")
            else:
                param_str = str(v).strip()
                # Replace None string with empty string
                if param_str.lower() in ('none', 'null', 'nan'):
                    valid_params.append("")
                else:
                    valid_params.append(param_str)
        
        # Create body component even if some params are empty (template might require all)
        if valid_params:  # If we have any params (even empty ones)
            body_component = {
                "type": "body",
                "parameters": [{"type": "text", "text": str(v) if v is not None else ""} for v in valid_params]
            }
            components = replace_component(components, "body", body_component)
            logger.debug(f"Created body component with {len(valid_params)} params: {valid_params}")
        else:
            logger.warning(f"No valid body params found for {recipient.get('phone_number')}")
    else:
        logger.warning(f"Body params is None or empty for {recipient.get('phone_number')}: {body_params}")

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
    #   "index": "0",
    #   "parameters": [{ "type": "text", "text": "..." }]
    # }
    if button_params is not None and len(button_params) > 0:
        # Normalise values and drop entries that are effectively empty
        cleaned_params: List[str] = []
        for v in button_params:
            if v is None:
                continue
            param_str = str(v).strip()
            if not param_str or param_str.lower() in ("none", "null", "nan"):
                continue
            cleaned_params.append(param_str)

        # If the button in the template requires a parameter, we MUST have at least one
        if button_requires_param and not cleaned_params:
            # Do NOT send an invalid payload to WhatsApp – raise so the caller can log
            raise ValueError(
                f"URL button requires a parameter but none provided for recipient {recipient.get('phone_number')}"
            )

        # If we have any valid params, build the button component
        if cleaned_params:
            button_index_str = str(button_index).strip() if button_index is not None else "0"
            button_sub_type_str = str(button_sub_type or "url").strip()

            button_component = {
                "type": "button",
                "sub_type": button_sub_type_str,
                "index": button_index_str,
                "parameters": [{"type": "text", "text": p} for p in cleaned_params]
            }
            components = replace_component(components, "button", button_component)
            logger.debug(
                f"Created button component with index={button_index_str}, "
                f"sub_type={button_sub_type_str}, params={cleaned_params}"
            )
        else:
            logger.warning(f"No usable button params found for {recipient.get('phone_number')}: {button_params}")
    else:
        # If template requires a button parameter but we have none, fail early
        if button_requires_param:
            raise ValueError(
                f"URL button requires a parameter but none provided for recipient {recipient.get('phone_number')}"
            )
        logger.debug(f"No button params for {recipient.get('phone_number')}; skipping button component")

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

    # Validate payload before returning
    # Ensure all required fields are present
    if not template_name:
        raise ValueError(f"Template name is required for recipient {recipient.get('phone_number')}")
    
    if not recipient.get('phone_number'):
        raise ValueError(f"Phone number is required for recipient")
    
    # Validate components structure
    validated_components = []
    for comp in components:
        if not isinstance(comp, dict):
            logger.warning(f"Invalid component type: {type(comp)}, skipping")
            continue
        if 'type' not in comp:
            logger.warning(f"Component missing 'type' field: {comp}, skipping")
            continue
        
        # Ensure parameters is a list
        if 'parameters' in comp:
            if not isinstance(comp['parameters'], list):
                logger.warning(f"Component parameters is not a list: {comp['parameters']}, converting")
                comp['parameters'] = [comp['parameters']] if comp['parameters'] else []
        
        validated_components.append(comp)
    
    payload = {
        "messaging_product": "whatsapp",
        "to": str(recipient['phone_number']).strip(),  # Ensure phone is string
        "type": "template",
        "template": {
            "name": str(template_name).strip(),
            "language": {"code": str(language_code).strip()},
            "components": validated_components  # Use validated components
        }
    }
    
    # Log the complete payload for debugging
    import json
    logger.debug(f"Built template payload for {recipient['phone_number']}")
    logger.debug(f"Payload components count: {len(validated_components)}")
    for idx, comp in enumerate(validated_components):
        comp_type = comp.get('type', 'unknown')
        params = comp.get('parameters', [])
        logger.debug(f"  Component {idx}: type={comp_type}, params_count={len(params)}")
        if comp_type == 'button':
            logger.debug(f"    Button index: {comp.get('index')}, sub_type: {comp.get('sub_type')}")
    
    # Final validation - check if payload can be JSON serialized
    try:
        json.dumps(payload)
    except (TypeError, ValueError) as e:
        logger.error(f"Payload is not JSON serializable: {e}")
        logger.error(f"Payload: {payload}")
        raise ValueError(f"Payload validation failed: {e}")
    
    logger.debug(f"Payload validation passed for {recipient['phone_number']}")
    
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