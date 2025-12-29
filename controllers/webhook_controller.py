from datetime import datetime
from http.client import HTTPException
import os
import json

from fastapi import Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import Any
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from controllers.utils.debug_window import debug_webhook_payload

# Webhook verification token
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "default_verify_token")

router = APIRouter(
    prefix="/webhook",
    tags=["Webhook"]
)

# Separate router for the second WhatsApp number
router2 = APIRouter(
    prefix="/webhook2",
    tags=["Webhook2"]
)


@router.post("")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive and process WhatsApp webhook messages.
    Similar to the webhook in web_socket.py but in a separate file.
    """
    try:
        # CRITICAL: Capture raw request body BEFORE JSON parsing to avoid truncation
        raw_body = await request.body()
        raw_body_str = raw_body.decode("utf-8", errors="replace")
        
        # Parse JSON from raw body
        try:
            body = json.loads(raw_body_str)
        except json.JSONDecodeError as e:
            print(f"[webhook_controller] ERROR - Invalid JSON in webhook payload: {e}")
            print(f"[webhook_controller] Raw body: {raw_body_str[:500]}...")
            return {"status": "error", "message": "Invalid JSON payload"}
        
        # Persist raw webhook payload to file for debugging/auditing
        try:
            log_dir = "webhook_logs"
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_path = os.path.join(log_dir, f"webhook_{ts}.json")

            # Write the complete raw body to ensure no truncation
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(raw_body_str)
                
            # Also create a formatted version for easier debugging
            formatted_path = os.path.join(log_dir, f"webhook_{ts}_formatted.json")
            try:
                formatted_json = json.dumps(body, ensure_ascii=False, indent=2, default=str)
                with open(formatted_path, "w", encoding="utf-8") as lf:
                    lf.write(formatted_json)
            except Exception as e:
                print(f"[webhook_controller] WARN - Could not create formatted log: {e}")

        except Exception as e:
            print(f"[webhook_controller] WARN - webhook logging failed: {e}")
        
        # Enhanced debugging for webhook payloads
        debug_webhook_payload(body, raw_body_str)
        
        # Check if this is a status update (not a message) - skip it
        if "entry" in body:
            value = body["entry"][0]["changes"][0]["value"]
            # If value contains 'statuses' but no 'messages' or 'contacts', it's a status update
            if "statuses" in value and ("messages" not in value or "contacts" not in value):
                print(f"[webhook_controller] DEBUG - Skipping status update webhook")
                return {"status": "ok", "message": "Status update ignored"}
        elif "statuses" in body and ("messages" not in body or "contacts" not in body):
            print(f"[webhook_controller] DEBUG - Skipping status update webhook (alternative structure)")
            return {"status": "ok", "message": "Status update ignored"}
        
        # Handle different payload structures
        phone_number_id = None
        value = None
        
        if "entry" in body:
            # Standard WhatsApp Business API webhook structure
            print(f"[webhook_controller] DEBUG - Using standard webhook structure")
            value = body["entry"][0]["changes"][0]["value"]
            
            # Verify we have messages and contacts
            if "messages" not in value or "contacts" not in value:
                print(f"[webhook_controller] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[webhook_controller] Available keys in value: {list(value.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = value["contacts"][0]
            message = value["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = value["metadata"]["display_phone_number"]
            
            # Extract phone_number_id from metadata
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            print(f"[webhook_controller] DEBUG - phone_number_id from metadata: {phone_number_id}")
        else:
            # Alternative payload structure (direct structure)
            print(f"[webhook_controller] DEBUG - Using alternative payload structure")
            
            # Verify we have messages and contacts
            if "messages" not in body or "contacts" not in body:
                print(f"[webhook_controller] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[webhook_controller] Available keys in body: {list(body.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = body["contacts"][0]
            message = body["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = body.get("phone_number_id", "367633743092037")
            phone_number_id = body.get("phone_number_id")
            print(f"[webhook_controller] DEBUG - phone_number_id from body: {phone_number_id}")
        
        # Extract message details
        message_type = message.get("type")
        message_id = message.get("id")
        timestamp = message.get("timestamp")
        
        print(f"[webhook_controller] INFO - Received message from {wa_id} ({sender_name}), type: {message_type}")
        
        # TODO: Add your message processing logic here
        # You can import and use the same handlers from web_socket.py if needed
        
        # Return success response
        return {"status": "ok", "message": "Webhook received and processed"}
        
    except Exception as e:
        print(f"[webhook_controller] ERROR - Exception in webhook handler: {e}")
        import traceback
        print(f"[webhook_controller] Traceback: {traceback.format_exc()}")
        return {"status": "failed", "error": str(e)}


@router.get("")
async def verify_webhook(request: Request):
    """
    Verify webhook subscription for WhatsApp Business API.
    This endpoint is called by Meta/Facebook during webhook setup.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[webhook_controller] WEBHOOK_VERIFIED")
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


# =============================================================================
# WEBHOOK 2 - For Second WhatsApp Business Number
# =============================================================================

@router2.post("")
async def receive_webhook2(request: Request, db: Session = Depends(get_db)):
    """
    Receive and process WhatsApp webhook messages for the second phone number.
    This is a separate webhook endpoint with different routing.
    """
    try:
        # CRITICAL: Capture raw request body BEFORE JSON parsing to avoid truncation
        raw_body = await request.body()
        raw_body_str = raw_body.decode("utf-8", errors="replace")
        
        # Parse JSON from raw body
        try:
            body = json.loads(raw_body_str)
        except json.JSONDecodeError as e:
            print(f"[webhook2] ERROR - Invalid JSON in webhook payload: {e}")
            print(f"[webhook2] Raw body: {raw_body_str[:500]}...")
            return {"status": "error", "message": "Invalid JSON payload"}
        
        # Persist raw webhook payload to file for debugging/auditing
        try:
            log_dir = "webhook_logs"
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_path = os.path.join(log_dir, f"webhook2_{ts}.json")

            # Write the complete raw body to ensure no truncation
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(raw_body_str)
                
            # Also create a formatted version for easier debugging
            formatted_path = os.path.join(log_dir, f"webhook2_{ts}_formatted.json")
            try:
                formatted_json = json.dumps(body, ensure_ascii=False, indent=2, default=str)
                with open(formatted_path, "w", encoding="utf-8") as lf:
                    lf.write(formatted_json)
            except Exception as e:
                print(f"[webhook2] WARN - Could not create formatted log: {e}")

        except Exception as e:
            print(f"[webhook2] WARN - webhook logging failed: {e}")
        
        # Enhanced debugging for webhook payloads
        debug_webhook_payload(body, raw_body_str)
        
        # Check if this is a status update (not a message) - skip it
        if "entry" in body:
            value = body["entry"][0]["changes"][0]["value"]
            # If value contains 'statuses' but no 'messages' or 'contacts', it's a status update
            if "statuses" in value and ("messages" not in value or "contacts" not in value):
                print(f"[webhook2] DEBUG - Skipping status update webhook")
                return {"status": "ok", "message": "Status update ignored"}
        elif "statuses" in body and ("messages" not in body or "contacts" not in body):
            print(f"[webhook2] DEBUG - Skipping status update webhook (alternative structure)")
            return {"status": "ok", "message": "Status update ignored"}
        
        # Handle different payload structures
        phone_number_id = None
        value = None
        
        if "entry" in body:
            # Standard WhatsApp Business API webhook structure
            print(f"[webhook2] DEBUG - Using standard webhook structure")
            value = body["entry"][0]["changes"][0]["value"]
            
            # Verify we have messages and contacts
            if "messages" not in value or "contacts" not in value:
                print(f"[webhook2] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[webhook2] Available keys in value: {list(value.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = value["contacts"][0]
            message = value["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = value["metadata"]["display_phone_number"]
            
            # Extract phone_number_id from metadata
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            print(f"[webhook2] DEBUG - phone_number_id from metadata: {phone_number_id}")
        else:
            # Alternative payload structure (direct structure)
            print(f"[webhook2] DEBUG - Using alternative payload structure")
            
            # Verify we have messages and contacts
            if "messages" not in body or "contacts" not in body:
                print(f"[webhook2] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[webhook2] Available keys in body: {list(body.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = body["contacts"][0]
            message = body["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = body.get("phone_number_id", "367633743092037")
            phone_number_id = body.get("phone_number_id")
            print(f"[webhook2] DEBUG - phone_number_id from body: {phone_number_id}")
        
        # Extract message details
        message_type = message.get("type")
        message_id = message.get("id")
        timestamp = message.get("timestamp")
        
        print(f"[webhook2] INFO - Received message from {wa_id} ({sender_name}), type: {message_type}, phone_id: {phone_number_id}")
        
        # TODO: Add your message processing logic here for the second number
        # You can import and use different handlers or route based on phone_number_id
        # This can have completely different logic than the first webhook
        
        # Return success response
        return {"status": "ok", "message": "Webhook2 received and processed"}
        
    except Exception as e:
        print(f"[webhook2] ERROR - Exception in webhook handler: {e}")
        import traceback
        print(f"[webhook2] Traceback: {traceback.format_exc()}")
        return {"status": "failed", "error": str(e)}


@router2.get("")
async def verify_webhook2(request: Request):
    """
    Verify webhook subscription for the second WhatsApp Business API number.
    This endpoint is called by Meta/Facebook during webhook setup.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[webhook2] WEBHOOK_VERIFIED")
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

