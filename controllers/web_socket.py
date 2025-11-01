from datetime import datetime, timedelta
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import re
import mimetypes
import asyncio
import os
import json
import requests
import uuid

from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from schemas.orders_schema import OrderItemCreate,OrderCreate, PaymentCreate
from services import customer_service, message_service, order_service
from services import payment_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from models.models import Message
from utils.whatsapp import send_message_to_waid
from utils.name_validator import validate_human_name
from utils.phone_validator import validate_indian_phone
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url, get_media_url

# =============================================================================
# WHATSAPP FLOW HANDLING
# =============================================================================
# WhatsApp Flows are designed in Meta Business Manager's Flow Builder.
# The flow fields, validation, and UI are defined there, not in this code.
# This code only handles the webhook response when users complete the flow.
from utils.razorpay_utils import create_razorpay_payment_link
from utils.ws_manager import manager

def debug_webhook_payload(body: Dict[str, Any], raw_body: str = None) -> None:
    """Enhanced debugging utility for webhook payloads"""
    try:
        print(f"[webhook_debug] Payload keys: {list(body.keys())}")
        
        if "entry" in body:
            entry = body["entry"][0] if body["entry"] else {}
            print(f"[webhook_debug] Entry ID: {entry.get('id', 'N/A')}")
            
            if "changes" in entry:
                change = entry["changes"][0] if entry["changes"] else {}
                print(f"[webhook_debug] Change field: {change.get('field', 'N/A')}")
                
                value = change.get("value", {})
                print(f"[webhook_debug] Value keys: {list(value.keys())}")
                
                if "messages" in value:
                    messages = value["messages"]
                    print(f"[webhook_debug] Message count: {len(messages)}")
                    
                    for i, msg in enumerate(messages):
                        print(f"[webhook_debug] Message {i}: type={msg.get('type', 'N/A')}, id={msg.get('id', 'N/A')}")
                        
                        if msg.get("type") == "interactive":
                            interactive = msg.get("interactive", {})
                            print(f"[webhook_debug] Interactive type: {interactive.get('type', 'N/A')}")
                            
                            if interactive.get("type") == "nfm_reply":
                                nfm = interactive.get("nfm_reply", {})
                                response_json = nfm.get("response_json", "")
                                print(f"[webhook_debug] NFM response_json length: {len(response_json)}")
                                print(f"[webhook_debug] NFM response_json preview: {response_json[:200]}...")
                                
                                # Check for truncation indicators
                                if response_json.endswith('...') or len(response_json) < 50:
                                    print(f"[webhook_debug] WARNING - Possible truncation detected!")
                                    
                                # Validate JSON structure
                                try:
                                    parsed = json.loads(response_json)
                                    print(f"[webhook_debug] NFM parsed keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'Not a dict'}")
                                    print(f"[webhook_debug] NFM parsed values: {parsed}")
                                    
                                    # Check for template variables
                                    has_template_vars = any("{{" in str(v) and "}}" in str(v) for v in parsed.values())
                                    if has_template_vars:
                                        print(f"[webhook_debug] WARNING - Template variables detected in parsed data!")
                                    
                                    # Check for empty values
                                    empty_values = [k for k, v in parsed.items() if not v or (isinstance(v, str) and not v.strip())]
                                    if empty_values:
                                        print(f"[webhook_debug] WARNING - Empty values found: {empty_values}")
                                        
                                except json.JSONDecodeError as e:
                                    print(f"[webhook_debug] ERROR - Invalid JSON in NFM response: {e}")
        
        if raw_body:
            print(f"[webhook_debug] Raw body length: {len(raw_body)}")
            print(f"[webhook_debug] Raw body preview: {raw_body[:300]}...")
            
    except Exception as e:
        print(f"[webhook_debug] ERROR - Debug function failed: {e}")

def debug_flow_data_extraction(flow_payload: Dict[str, Any], extracted_data: Dict[str, Any]) -> None:
    """Debug flow data extraction process"""
    try:
        print(f"[flow_debug] Flow payload keys: {list(flow_payload.keys())}")
        print(f"[flow_debug] Flow payload values: {flow_payload}")
        print(f"[flow_debug] Extracted data keys: {list(extracted_data.keys())}")
        print(f"[flow_debug] Extracted data values: {list(extracted_data.values())}")
        
        # Check for common field patterns
        common_fields = ["name", "phone", "address", "city", "state", "pincode", "zipcode"]
        found_fields = []
        for field in common_fields:
            if any(field.lower() in key.lower() for key in flow_payload.keys()):
                found_fields.append(field)
        
        print(f"[flow_debug] Common fields found in payload: {found_fields}")
        
        # Check for nested data structures
        for key, value in flow_payload.items():
            if isinstance(value, dict):
                print(f"[flow_debug] Nested object '{key}': {value}")
            elif isinstance(value, list):
                print(f"[flow_debug] Array '{key}': {value}")
                
    except Exception as e:
        print(f"[flow_debug] ERROR - Debug function failed: {e}")
from utils.shopify_admin import update_variant_price
from utils.address_validator import analyze_address, format_errors_for_user
from controllers.components.welcome_flow import run_welcome_flow, trigger_buy_products_from_welcome
from controllers.components.treament_flow import run_treament_flow, run_treatment_buttons_flow
from controllers.components.interactive_type import run_interactive_type
from controllers.components.lead_appointment_flow import run_lead_appointment_flow
from controllers.components.products_flow import run_buy_products_flow

router = APIRouter()


# In-memory store: { wa_id: True/False }
awaiting_address_users = {}
# Track whether we've already nudged the user to use the form to avoid repeats
address_nudge_sent = {}

# In-memory appointment scheduling state per user
# Structure: { wa_id: { "date": "YYYY-MM-DD" } }
appointment_state = {}

# In-memory lead appointment flow state per user
# Structure: { wa_id: { "selected_city": str, "selected_clinic": str, "custom_date": str, "waiting_for_custom_date": bool, "clinic_id": str } }
lead_appointment_state = {}

# Flow token storage
flow_tokens = {}

def generate_flow_token(wa_id: str) -> str:
    """Generate a unique flow token for a user"""
    flow_token = str(uuid.uuid4())
    flow_tokens[wa_id] = flow_token
    return flow_token


# WebSocket endpoint
@router.websocket("/channel")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keeping connection alive; log pings occasionally
            try:
                _ = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except RuntimeError:
                # Happens if we try to receive after disconnect
                break
            except Exception:
                # Ignore non-text frames or transient errors
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)

VERIFY_TOKEN = "Oliva@123"

# Legacy address text guidance removed per new Provide Address flow


# Legacy date list removed. Week/day selection is handled in controllers.components.interactive_type


async def _send_address_flow_directly(wa_id: str, db: Session, customer_id=None):
    """Send smart address selection - check for saved addresses first"""
    try:
        # First check if user has saved addresses
        if customer_id:
            from services.address_service import get_customer_addresses
            saved_addresses = get_customer_addresses(db, customer_id)
            
            if saved_addresses:
                # User has saved addresses - show smart selection
                await _send_smart_address_selection(wa_id, db, saved_addresses, customer_id)
                return
        
        # No saved addresses or customer_id not provided - send address form directly
        await _send_address_form_directly(wa_id, db, customer_id)
        
    except Exception as e:
        print(f"Error in _send_address_flow_directly: {e}")
        await send_message_to_waid(wa_id, "❌ Unable to send address form right now. Please try again later.", db)


async def _send_smart_address_selection(wa_id: str, db: Session, saved_addresses: list, customer_id):
    """Send interactive message with saved addresses and options.

    If multiple addresses exist, send a list message where each row selects that address.
    Also include an action to add a new address.
    """
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address selection right now. Please try again later.", db)
            return

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        # Build a list of saved addresses (max 10 per WhatsApp constraints)
        rows = []
        for addr in saved_addresses[:10]:
            title = f"{addr.full_name[:35]}"  # titles are limited; keep concise
            subtitle = f"{addr.house_street[:60]} | {addr.city} - {addr.pincode}"
            rows.append({
                "id": f"use_address_{addr.id}",
                "title": title,
                "description": subtitle,
            })

        # Create interactive list with an extra row to add a new address
        rows.append({
            "id": "add_new_address",
            "title": "➕ Add New Address",
            "description": "Provide a different delivery address",
        })

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "📍 Choose Delivery Address"},
                "body": {"text": "Select one of your saved addresses or add a new one."},
                "footer": {"text": "You can manage addresses anytime."},
                "action": {
                    "button": "Select",
                    "sections": [
                        {
                            "title": "Saved Addresses",
                            "rows": rows
                        }
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                msg_id = resp.json()["messages"][0]["id"]
                message = MessageCreate(
                    message_id=msg_id,
                    from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Address selection sent",
                    timestamp=datetime.now(),
                    customer_id=customer_id
                )
                message_service.create_message(db, message)
                db.commit()  # Explicitly commit the transaction
                
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address selection sent",
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                print(f"Error saving address selection message: {e}")
        else:
            print(f"Failed to send address selection: {resp.text}")
            # Fallback to direct address form
            await _send_address_form_directly(wa_id, db, customer_id)
            
    except Exception as e:
        print(f"Error in _send_smart_address_selection: {e}")
        # Fallback to direct address form
        await _send_address_form_directly(wa_id, db, customer_id)


async def _send_address_form_directly(wa_id: str, db: Session, customer_id=None):
    """Send address collection flow directly (original function)"""
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address form right now. Please try again later.", db)
            return

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        # Send address flow directly
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "flow",
                "header": {"type": "text", "text": "📍 Address Collection"},
                "body": {"text": "Please provide your delivery address using the form below."},
                "footer": {"text": "All fields are required for delivery"},
                "action": {
                    "name": "flow",
                    "parameters": {
                        "flow_message_version": "3",
                        "flow_id": "1314521433687006",
                        "flow_cta": "Provide Address",
                        "flow_token": generate_flow_token(wa_id)
                    }
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                flow_msg_id = resp.json()["messages"][0]["id"]
                flow_message = MessageCreate(
                    message_id=flow_msg_id,
                    from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Address collection flow sent",
                    timestamp=datetime.now(),
                    customer_id=customer_id
                )
                message_service.create_message(db, flow_message)
                db.commit()  # Explicitly commit the transaction
                
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address collection flow sent",
                    "timestamp": datetime.now().isoformat()
                })
                
                # Mark user as awaiting address
                awaiting_address_users[wa_id] = True
                address_nudge_sent[wa_id] = False
                
            except Exception as e:
                print(f"Error saving address flow message: {e}")
        else:
            print(f"Failed to send address flow: {resp.text}")
            await send_message_to_waid(wa_id, "❌ Unable to send address form right now. Please try again later.", db)
    except Exception as e:
        print(f"Error in _send_address_form_directly: {e}")
        await send_message_to_waid(wa_id, "❌ Unable to send address form right now. Please try again later.", db)


async def send_time_buttons(wa_id: str, db: Session):
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to fetch time slots right now.", db)
            return {"success": False}
        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        selected_date = (appointment_state.get(wa_id) or {}).get("date")
        date_note = f" for {selected_date}" if selected_date else ""

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": f"Great! Now choose a preferred time slot \u23F0{date_note}"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "time_10_00", "title": "10:00 AM"}},
                        {"type": "reply", "reply": {"id": "time_14_00", "title": "2:00 PM"}},
                        {"type": "reply", "reply": {"id": "time_18_00", "title": "6:00 PM"}}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                display_from = os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                await manager.broadcast({
                    "from": display_from,
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Choose a preferred time slot",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "buttons", "options": ["10:00 AM", "2:00 PM", "6:00 PM"]}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send time slots. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending time slots: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def _confirm_appointment(wa_id: str, db: Session, date_iso: str, time_label: str):
    try:
        # Get referrer information for center details
        center_info = ""
        try:
            from services.referrer_service import referrer_service
            referrer = referrer_service.get_referrer_by_wa_id(db, wa_id)
            if referrer and referrer.center_name:
                center_info = f" at {referrer.center_name}, {referrer.location}"
        except Exception:
            pass
        
        # Prepare confirmation prompt with pre-filled name/phone (no thank-you yet)
        try:
            from services.customer_service import get_customer_record_by_wa_id
            customer = get_customer_record_by_wa_id(db, wa_id)
            display_name = (customer.name.strip() if customer and isinstance(customer.name, str) else None) or "there"
        except Exception:
            display_name = "there"
        # Derive phone from wa_id as +91XXXXXXXXXX if applicable
        try:
            import re as _re
            digits = _re.sub(r"\D", "", wa_id)
            last10 = digits[-10:] if len(digits) >= 10 else None
            display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
        except Exception:
            display_phone = wa_id

        confirm_msg = (
            f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*"
        )
        await send_message_to_waid(wa_id, confirm_msg, db)

        # Store selection in state until user confirms Yes/No
        try:
            appointment_state[wa_id] = {"date": date_iso, "time": time_label}
        except Exception:
            pass

        # Follow-up interactive Yes/No confirmation buttons
        try:
            from services.whatsapp_service import get_latest_token
            from config.constants import get_messages_url
            token_entry_btn = get_latest_token(db)
            if token_entry_btn and token_entry_btn.token:
                access_token_btn = token_entry_btn.token
                phone_id_btn = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                headers_btn = {"Authorization": f"Bearer {access_token_btn}", "Content-Type": "application/json"}
                payload_btn = {
                    "messaging_product": "whatsapp",
                    "to": wa_id,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": "Are your name and contact number correct? "},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes"}},
                                {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}},
                            ]
                        },
                    },
                }
                requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                try:
                    await manager.broadcast({
                        "from": "system",
                        "to": wa_id,
                        "type": "interactive",
                        "message": "Are your name and contact number correct? ",
                        "timestamp": datetime.now().isoformat(),
                        "meta": {"kind": "buttons", "options": ["Yes", "No"]},
                    })
                except Exception:
                    pass
        except Exception:
            pass
        # Do NOT clear state here; we need it when user presses Yes/No
        # Broadcast
        try:
            await manager.broadcast({
                "from": "system",
                "to": wa_id,
                "type": "system",
                "message": f"Appointment preference captured: {date_iso} {time_label}",
                "timestamp": datetime.now().isoformat()
            })
        except Exception:
            pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _upload_header_image(access_token: str, image_path_or_url: str, phone_id: str) -> str:
    try:
        content = None
        filename = None
        content_type = None

        # Local file path
        if os.path.isfile(image_path_or_url):
            filename = os.path.basename(image_path_or_url)
            content_type = mimetypes.guess_type(image_path_or_url)[0] or "image/jpeg"
            with open(image_path_or_url, "rb") as f:
                content = f.read()
        else:
            # Assume URL
            resp = requests.get(image_path_or_url, timeout=15)
            if resp.status_code != 200:
                return None
            content = resp.content
            filename = os.path.basename(image_path_or_url.split("?")[0]) or "welcome.jpg"
            content_type = resp.headers.get("Content-Type") or mimetypes.guess_type(image_path_or_url)[0] or "image/jpeg"

        files = {
            "file": (filename, content, content_type),
            "messaging_product": (None, "whatsapp")
        }
        up = requests.post(get_media_url(phone_id), headers={"Authorization": f"Bearer {access_token}"}, files=files, timeout=20)
        if up.status_code == 200:
            return up.json().get("id")
    except Exception:
        return None
    return None

@router.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    try:
        # CRITICAL: Capture raw request body BEFORE JSON parsing to avoid truncation
        raw_body = await request.body()
        raw_body_str = raw_body.decode("utf-8", errors="replace")
        
        # Parse JSON from raw body
        try:
            body = json.loads(raw_body_str)
        except json.JSONDecodeError as e:
            print(f"[ws_webhook] ERROR - Invalid JSON in webhook payload: {e}")
            print(f"[ws_webhook] Raw body: {raw_body_str[:500]}...")
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
                print(f"[ws_webhook] WARN - Could not create formatted log: {e}")

        except Exception as e:
            print(f"[ws_webhook] WARN - webhook logging failed: {e}")
        
        # Enhanced debugging for webhook payloads
        debug_webhook_payload(body, raw_body_str)
        
        # Check if this is a status update (not a message) - skip it
        if "entry" in body:
            value = body["entry"][0]["changes"][0]["value"]
            # If value contains 'statuses' but no 'messages' or 'contacts', it's a status update
            if "statuses" in value and ("messages" not in value or "contacts" not in value):
                print(f"[ws_webhook] DEBUG - Skipping status update webhook")
                return {"status": "ok", "message": "Status update ignored"}
        elif "statuses" in body and ("messages" not in body or "contacts" not in body):
            print(f"[ws_webhook] DEBUG - Skipping status update webhook (alternative structure)")
            return {"status": "ok", "message": "Status update ignored"}
        
        # Handle different payload structures
        if "entry" in body:
            # Standard WhatsApp Business API webhook structure
            print(f"[ws_webhook] DEBUG - Using standard webhook structure")
            value = body["entry"][0]["changes"][0]["value"]
            
            # Verify we have messages and contacts
            if "messages" not in value or "contacts" not in value:
                print(f"[ws_webhook] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[ws_webhook] Available keys in value: {list(value.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = value["contacts"][0]
            message = value["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = value["metadata"]["display_phone_number"]
        else:
            # Alternative payload structure (direct structure)
            print(f"[ws_webhook] DEBUG - Using alternative payload structure")
            
            # Verify we have messages and contacts
            if "messages" not in body or "contacts" not in body:
                print(f"[ws_webhook] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[ws_webhook] Available keys in body: {list(body.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = body["contacts"][0]
            message = body["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = body.get("phone_number_id", "367633743092037")
            print(f"[ws_webhook] DEBUG - phone_number_id: {to_wa_id}")
        timestamp = datetime.fromtimestamp(int(message["timestamp"]))
        message_type = message["type"]
        message_id = message["id"]
        
        # Initialize interactive variables for all message types
        interactive = message.get("interactive", {}) if message_type == "interactive" else {}
        i_type = interactive.get("type") if message_type == "interactive" else None

        # Derive a text body for non-text messages (interactive/list/button) so parsers work
        body_text = ""
        try:
            if message_type == "text":
                body_text = message[message_type].get("body", "")
            elif message_type == "interactive":
                it = message.get("interactive", {})
                if it.get("type") == "button_reply":
                    br = it.get("button_reply", {})
                    # Include both title and id to help downstream parsers (e.g., time_10_00)
                    body_text = " ".join(filter(None, [br.get("title"), br.get("id")]))
                elif it.get("type") == "list_reply":
                    lr = it.get("list_reply", {})
                    # Include both title and id to help downstream parsers (e.g., date_2025-10-01)
                    body_text = " ".join(filter(None, [lr.get("title"), lr.get("id")]))
                elif it.get("type") == "nfm_reply":
                    # Handle Native Flow Message reply - extract meaningful data
                    nfm = it.get("nfm_reply", {})
                    response_json = nfm.get("response_json", "{}")
                    try:
                        response_data = json.loads(response_json)
                        # Create a meaningful body text from the form data using mapped field names
                        form_fields = []
                        for key, value in response_data.items():
                            if value and str(value).strip() and not ("{{" in str(value) and "}}" in str(value)):
                                # Use user-friendly field names for display
                                display_names = {
                                    "full_name": "Name",
                                    "phone_number": "Phone", 
                                    "house_street": "Address",
                                    "pincode": "Pincode",
                                    "city": "City",
                                    "state": "State"
                                }
                                display_key = display_names.get(key, key)
                                form_fields.append(f"{display_key}: {value}")
                        body_text = " | ".join(form_fields) if form_fields else "Form submitted"
                        print(f"[ws_webhook] DEBUG - NFM body_text: {body_text}")
                    except Exception as e:
                        body_text = "Form submitted"
                        print(f"[ws_webhook] DEBUG - NFM body_text fallback: {e}")
                elif it.get("type") == "flow":
                    # Handle flow response
                    flow_response = it.get("flow_response", {})
                    flow_payload = flow_response.get("flow_action_payload", {})
                    if flow_payload:
                        form_fields = []
                        for key, value in flow_payload.items():
                            if value and str(value).strip():
                                form_fields.append(f"{key}: {value}")
                        body_text = " | ".join(form_fields) if form_fields else "Flow submitted"
                    else:
                        body_text = "Flow submitted"
            elif message_type == "button":
                btn = message.get("button", {})
                body_text = btn.get("text") or btn.get("payload") or ""
        except Exception:
            body_text = ""
        handled_text = False

        # Check prior messages first (before any early returns)
        prior_messages = message_service.get_messages_by_wa_id(db, wa_id)

        # Fetch or create customer
        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Track referrer information on EVERY message
        if body_text:
            try:
                from services.referrer_service import referrer_service
                
                # Get referrer URL from request headers if available
                referrer_url = (
                    request.headers.get("referer", "")
                    or request.headers.get("referrer", "")
                    or request.headers.get("x-forwarded-referer", "")
                    or request.headers.get("x-forwarded-referrer", "")
                    or request.headers.get("origin", "")
                )

                # Also include any query params on the webhook URL itself (defensive in prod)
                request_query = str(request.url.query) if getattr(request, "url", None) else ""
                combined_body = (
                    f"{body_text}&{request_query}" if request_query else body_text
                )
                
                # Track message interaction and extract UTM parameters
                referrer_record = referrer_service.track_message_interaction(db, wa_id, combined_body, referrer_url)
                
                if referrer_record:
                    print(f"Referrer tracking completed for {wa_id}")
                    try:
                        print(f"Center: {referrer_record.center_name}")
                        print(f"Location: {referrer_record.location}")
                        print(f"Appointment Date: {getattr(referrer_record, 'appointment_date', None)}")
                        print(f"Appointment Time: {getattr(referrer_record, 'appointment_time', None)}")
                        print(f"Treatment: {getattr(referrer_record, 'treatment_type', None)}")
                    except Exception:
                        pass
                else:
                    # Add explicit diagnostics to understand prod behavior
                    print("Referrer tracking yielded no record. Diagnostics:")
                    print(f"Headers referer={request.headers.get('referer', '')}")
                    print(f"Headers referrer={request.headers.get('referrer', '')}")
                    print(f"Headers x-forwarded-referer={request.headers.get('x-forwarded-referer', '')}")
                    print(f"Headers x-forwarded-referrer={request.headers.get('x-forwarded-referrer', '')}")
                    print(f"origin={request.headers.get('origin', '')}")
                    print(f"request_query={request_query}")
                    
            except Exception as e:
                print(f"Error tracking referrer: {e}")
                import traceback
                traceback.print_exc()

        # Check for appointment booking in any message (not just first message)
        if body_text:
            try:
                from services.referrer_service import referrer_service
                
                # Extract appointment information from message
                appointment_info = referrer_service.extract_appointment_info_from_message(body_text)
                
                # Allow interim updates (date-only or time-only), and finalize when both are present
                if appointment_info['appointment_date'] or appointment_info['appointment_time']:
                    print(f"Appointment booking detected for {wa_id}: {appointment_info}")
                    
                    # Try to update existing referrer record
                    # Preserve existing treatment if the current message doesn't include one
                    try:
                        existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                        existing_treat = getattr(existing_ref, 'treatment_type', None) if existing_ref else None
                    except Exception:
                        existing_treat = None

                    updated_referrer = referrer_service.update_appointment_booking(
                        db, 
                        wa_id, 
                        appointment_info['appointment_date'],
                        appointment_info['appointment_time'] or '',
                        appointment_info['treatment_type'] or existing_treat or ''
                    )
                    
                    if updated_referrer:
                        print(f"Successfully updated appointment booking for {wa_id}")
                        print(f"Appointment: {updated_referrer.appointment_date} at {updated_referrer.appointment_time}")
                        print(f"Treatment: {updated_referrer.treatment_type}")
                    else:
                        # Do not create a new record here; initial message should have created it
                        print(f"No existing referrer record for {wa_id}; skipping creation to avoid duplicates")
                    
            except Exception as e:
                print(f"Error processing appointment booking: {e}")
                import traceback
                traceback.print_exc()

        # 1️⃣ Onboarding prompt (only for first message)
        # if len(prior_messages) == 0:
        #     await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)

        # Address flow gating removed to allow other flows to proceed after "Provide Address"

        # 3️⃣ LEAD-TO-APPOINTMENT FLOW - handle Meta ad triggered flows FIRST (priority check)
        # Check for starting point messages before treatment flow to give lead appointment flow priority
        handled_text = False
        if message_type == "text" and body_text:
            # Quick check for lead appointment starting point patterns
            # Normalize Unicode characters for better matching
            try:
                import unicodedata
                body_text_normalized = unicodedata.normalize('NFKC', body_text)
                # Replace various apostrophe/quote characters with standard apostrophe (handle all Unicode variants)
                # U+2019 (right single quotation mark), U+2018 (left single quotation mark), U+02BC (modifier letter apostrophe)
                body_text_normalized = body_text_normalized.replace("'", "'")  # Right single quotation mark → standard apostrophe
                body_text_normalized = body_text_normalized.replace("'", "'")  # Left single quotation mark → standard apostrophe
                body_text_normalized = body_text_normalized.replace("'", "'")  # Modifier letter apostrophe → standard apostrophe
                body_text_normalized = body_text_normalized.replace("'", "'")  # Any other variants
                body_text_normalized = body_text_normalized.replace(""", '"').replace(""", '"')
            except Exception:
                # Fallback: replace common apostrophe variants
                body_text_normalized = body_text.replace("'", "'").replace("'", "'").replace("'", "'")
            
            normalized_check = ' '.join(body_text_normalized.lower().strip().rstrip('.').split())
            
            # Debug logging for server troubleshooting
            print(f"[lead_appointment_flow] DEBUG - Checking message: wa_id={wa_id}")
            print(f"[lead_appointment_flow] DEBUG - Original body_text (first 150 chars): '{body_text[:150]}'")
            print(f"[lead_appointment_flow] DEBUG - Normalized (first 150 chars): '{normalized_check[:150]}'")
            
            # Check for pattern match (more flexible)
            # Only match standard ad link messages for lead appointment flow
            # Location/clinic inquiry messages ("want to know more about services in...") should go to TREATMENT flow
            has_pattern = (
                "i saw your ad for oliva" in normalized_check 
                and "want to know more" in normalized_check
            )
            
            # Also check exact matches (but with normalized apostrophes)
            exact_matches = [
                "hi! i saw your ad for oliva's hair regrowth treatments and want to know more",
                "hi! i saw your ad for oliva's precision+ laser hair reduction and want to know more",
                "hi! i saw your ad for oliva's skin brightening treatments and want to know more",
                "hi! i saw your ad for oliva's acne & scar treatments and want to know more",
                "hi! i saw your ad for oliva's skin boosters and want to know more",
            ]
            # Normalize apostrophes in exact matches too
            normalized_exact_matches = [m.replace("'", "'").replace("'", "'") for m in exact_matches]
            
            is_exact_match = normalized_check in normalized_exact_matches
            is_lead_starting_point = has_pattern or is_exact_match
            
            print(f"[lead_appointment_flow] DEBUG - Pattern check: has_pattern={has_pattern}")
            print(f"[lead_appointment_flow] DEBUG - Exact match check: is_exact_match={is_exact_match}")
            print(f"[lead_appointment_flow] DEBUG - Final result: is_lead_starting_point={is_lead_starting_point}, wa_id={wa_id}")
            print(f"[lead_appointment_flow] DEBUG - Note: Location inquiry messages (like 'want to know more about services in...') route to TREATMENT flow")
            
            if is_lead_starting_point:
                print(f"[lead_appointment_flow] DEBUG - ✅ Starting point detected! Running lead appointment flow...")
                # Lead appointment flow has priority - skip treatment flow for these messages
                try:
                    lead_result = await run_lead_appointment_flow(
                        db,
                        wa_id=wa_id,
                        message_type=message_type,
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id=to_wa_id,
                        body_text=body_text,
                        timestamp=timestamp,
                        customer=customer,
                        interactive=interactive,
                        i_type=i_type,
                    )
                    lead_status = (lead_result or {}).get("status")
                    print(f"[lead_appointment_flow] DEBUG - Lead flow result: status={lead_status}, result={lead_result}")
                    
                    if lead_status not in {"skipped", "error"}:
                        print(f"[lead_appointment_flow] DEBUG - ✅ Lead flow handled successfully, returning result")
                        return lead_result
                    else:
                        print(f"[lead_appointment_flow] DEBUG - ⚠️ Lead flow returned skipped/error: {lead_status}")
                    
                    handled_text = lead_status in {"auto_welcome_sent", "proceed_to_city_selection", "proceed_to_clinic_location", "proceed_to_time_slot", "waiting_for_custom_date", "callback_initiated", "lead_created_no_callback", "thank_you_sent", "week_list_sent", "day_list_sent", "time_slots_sent", "times_sent"}
                except Exception as e:
                    print(f"[lead_appointment_flow] ERROR - Exception in lead appointment flow: {str(e)}")
                    import traceback
                    print(f"[lead_appointment_flow] ERROR - Traceback: {traceback.format_exc()}")
                    # Don't fail completely, let other flows try

        # 3️⃣ AUTO WELCOME VALIDATION - extracted to component function
        if not handled_text and message_type == "text":
            result = await run_treament_flow(
                db,
                message_type=message_type,
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                body_text=body_text,
                timestamp=timestamp,
                customer=customer,
                wa_id=wa_id,
                value=value,
                sender_name=sender_name,
            )
            status_val = (result or {}).get("status")
            if status_val in {"welcome_sent", "welcome_failed"}:
                return result
            handled_text = status_val in {"handled"}

        # 3️⃣ LEAD-TO-APPOINTMENT FLOW - handle other lead appointment triggers
        if not handled_text:
            lead_result = await run_lead_appointment_flow(
                db,
                wa_id=wa_id,
                message_type=message_type,
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                body_text=body_text,
                timestamp=timestamp,
                customer=customer,
                interactive=interactive,
                i_type=i_type,
            )
            lead_status = (lead_result or {}).get("status")
            if lead_status not in {"skipped", "error"}:
                return lead_result
            handled_text = lead_status in {"auto_welcome_sent", "proceed_to_city_selection", "proceed_to_clinic_location", "proceed_to_time_slot", "waiting_for_custom_date", "callback_initiated", "lead_created_no_callback", "thank_you_sent", "week_list_sent", "day_list_sent", "time_slots_sent", "times_sent"}

        # Manual date-time fallback parsing before other generic text handling
        if message_type == "text" and not handled_text:
            try:
                # Pattern: DD-MM-YYYY, HH:MM AM/PM (also supports / as separator)
                m_dt = re.search(r"\b(\d{1,2})[\-\/](\d{1,2})[\-\/]?(\d{2,4})\b\s*,?\s*(\d{1,2}):(\d{2})\s*([APap][Mm])", body_text)
                m_d = re.search(r"\b(\d{1,2})[\-\/]((\d{1,2}))[\-\/]?(\d{2,4})\b", body_text)
                if m_dt:
                    dd, mm, yyyy, hh, mins, ampm = m_dt.groups()
                    yyyy = yyyy if len(yyyy) == 4 else ("20" + yyyy)
                    date_iso = f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
                    time_label = f"{int(hh):02d}:{int(mins):02d} {ampm.upper()}"
                    appointment_state[wa_id] = {"date": date_iso}
                    await _confirm_appointment(wa_id, db, date_iso, time_label)
                    return {"status": "appointment_captured", "message_id": message_id}
                elif m_d:
                    dd, mm, _, yyyy = m_d.groups()
                    yyyy = yyyy if len(yyyy) == 4 else ("20" + yyyy)
                    date_iso = f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
                    appointment_state[wa_id] = {"date": date_iso}
                    await send_message_to_waid(wa_id, f"✅ Date noted: {date_iso}", db)
                    await send_time_buttons(wa_id, db)
                    return {"status": "date_selected", "message_id": message_id}
            except Exception:
                pass

        # Handle dummy payment request
        if message_type == "text" and body_text:
            text_lower = body_text.lower().strip()
            if "dummy payment" in text_lower or "test payment" in text_lower:
                try:
                    from services.dummy_payment_service import DummyPaymentService
                    dummy_service = DummyPaymentService(db)
                    
                    # Create dummy payment link
                    result = await dummy_service.create_dummy_payment_link(
                        wa_id=wa_id,
                        customer_name=getattr(customer, "name", None)
                    )
                    
                    if result.get("success"):
                        print(f"[dummy_payment] Dummy payment link created: {result.get('payment_url')}")
                    else:
                        print(f"[dummy_payment] Failed to create dummy payment: {result.get('error')}")
                        await send_message_to_waid(wa_id, "❌ Failed to create test payment link.", db)
                    
                    return {"status": "dummy_payment_sent", "message_id": message_id}
                except Exception as e:
                    print(f"[dummy_payment] Error: {e}")
                    await send_message_to_waid(wa_id, "❌ Error creating test payment link.", db)
                    return {"status": "dummy_payment_failed", "message_id": message_id}

        # 4️⃣ Regular text messages - ALWAYS save to database regardless of handling
        if message_type == "text":
            # Check if already saved to avoid duplicates
            existing_msg = db.query(Message).filter(Message.message_id == message_id).first()
            if not existing_msg:
                inbound_text_msg = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type="text",
                    body=body_text,
                    timestamp=timestamp,
                    customer_id=customer.id
                )
                message_service.create_message(db, inbound_text_msg)
                db.commit()  # Explicitly commit the transaction
                
                # Only mark customer as replied if they have previous OUTBOUND messages from us
                # This prevents clearing follow-ups for initial conversation-starting messages
                # The follow-up will be scheduled AFTER this check, so we preserve it for initial messages
                try:
                    from services.followup_service import mark_customer_replied as _mark_replied
                    
                    # Check if there are any outbound messages from us before this inbound message
                    # Only mark as replied if they're actually replying to something we sent earlier
                    our_phone = os.getenv("WHATSAPP_PHONE_ID", "917729992376")
                    has_outbound_before = db.query(Message).filter(
                        Message.customer_id == customer.id,
                        Message.from_wa_id == our_phone,  # Messages we sent
                        Message.timestamp < timestamp  # Before this inbound message
                    ).first() is not None
                    
                    if has_outbound_before:
                        _mark_replied(db, customer_id=customer.id)
                        print(f"[ws_webhook] DEBUG - Customer {wa_id} replied after our message - cleared follow-up")
                    else:
                        # This is an initial message - don't clear follow-up (it will be scheduled by treatment flow)
                        print(f"[ws_webhook] DEBUG - Customer {wa_id} initial message - preserving scheduled follow-up")
                except Exception as e:
                    print(f"[ws_webhook] WARNING - Could not check if customer replied: {e}")
                    # If error, default to NOT clearing follow-up for safety
                    pass
                print(f"[ws_webhook] DEBUG - Inbound text message saved to database:")
                print(f"  - Message ID: {message_id}")
                print(f"  - From: {from_wa_id}")
                print(f"  - To: {to_wa_id}")
                print(f"  - Type: text")
                print(f"  - Body: {body_text}")
                print(f"  - Timestamp: {timestamp}")
                print(f"  - Customer ID: {customer.id}")
            
            # If we are waiting for user details (after confirm_no in treatment flow), handle now
            try:
                from controllers.web_socket import lead_appointment_state as _lead_state  # type: ignore
                waiting_details = ((_lead_state.get(wa_id) or {}).get("waiting_for_user_details"))
            except Exception:
                waiting_details = False

            if waiting_details:
                try:
                    from controllers.components.lead_appointment_flow.user_details import handle_user_details_input  # type: ignore
                    result = await handle_user_details_input(db=db, wa_id=wa_id, details_text=body_text, customer=customer)
                    return {"status": "user_details_handled", **result}
                except Exception:
                    pass

            # Always broadcast to WebSocket (even if already saved)
            if not handled_text:  # Only broadcast if not already handled by treatment flow
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": "text",
                    "message": body_text,
                    "timestamp": timestamp.isoformat()
                })

            # Catalog link is sent only on explicit button clicks; no text keyword trigger

        # 4️⃣ Hi/Hello auto-template (only if treatment flow didn't already handle)
        if not handled_text:
            welcome_result = await run_welcome_flow(
                db,
                message_type=message_type,
                body_text=body_text,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                sender_name=sender_name,
                customer=customer,
            )
            # no early return needed; this is an optional greeting handler

        # Send onboarding prompt on very first message from this WA ID
        # if len(prior_messages) == 0:
        #     await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)
      


        if message_type == "order":
            order = message["order"]
            order_items = [
                OrderItemCreate(
                    product_retailer_id=prod["product_retailer_id"],
                    quantity=prod["quantity"],
                    item_price=prod.get("item_price"),
                    currency=prod.get("currency")
                ) for prod in order["product_items"]
            ]

            # Check if this order addition is happening after a modify order action
            # by checking if the latest order has modification_started_at set
            is_modification = False
            try:
                # Use a separate session to avoid transaction conflicts
                from database.db import SessionLocal
                temp_db = SessionLocal()
                try:
                    latest_order = (
                        temp_db.query(order_service.Order)
                        .filter(order_service.Order.customer_id == customer.id)
                        .order_by(order_service.Order.timestamp.desc())
                        .first()
                    )
                    if latest_order and latest_order.modification_started_at:
                        is_modification = True
                finally:
                    temp_db.close()
            except Exception as e:
                print(f"[webhook] Error checking modification status: {e}")
                # Continue without modification flag if check fails

            # Merge into latest open order (if any); else create a new one
            try:
                order_obj = order_service.merge_or_create_order(
                    db,
                    customer_id=customer.id,
                    catalog_id=order.get("catalog_id"),
                    timestamp=timestamp,
                    items=order_items,
                    is_modification=is_modification,
                )
                print(f"[webhook] Order processed successfully: {order_obj.id}")
            except Exception as e:
                print(f"[webhook] Error processing order: {e}")
                # Rollback and try to continue
                db.rollback()
                return {"status": "failed", "error": f"Order processing failed: {str(e)}"}

            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "order",
                "catalog_id": order["catalog_id"],
                "products": order["product_items"],
                "timestamp": timestamp.isoformat(),
            })

            # After cart selection, ask the user to Modify / Cancel / Proceed
            try:
                from controllers.components.products_flow import send_cart_next_actions  # type: ignore
                await send_cart_next_actions(db, wa_id=wa_id)
            except Exception as e:
                print(f"[webhook] Error sending cart actions: {e}")
                # As a fallback, keep legacy behavior of sending address flow directly
                try:
                    await _send_address_flow_directly(wa_id, db, customer_id=customer.id)
                except Exception as fallback_error:
                    print(f"[webhook] Fallback address flow also failed: {fallback_error}")
                    await send_message_to_waid(wa_id, "✅ Items added to cart! Please proceed with checkout.", db)
        elif message_type == "location":
            location = message["location"]
            location_name = location.get("name", "")
            location_address = location.get("address", "")

            # convert to float safely
            latitude = float(location["latitude"]) if "latitude" in location else None
            longitude = float(location["longitude"]) if "longitude" in location else None

            # body fallback
            if location_name or location_address:
                location_body = ", ".join(filter(None, [location_name, location_address]))
            else:
                location_body = f"Shared Location - Lat: {latitude}, Lng: {longitude}"

            # NEW: Check if this is part of address collection
            try:
                from services.address_collection_service import AddressCollectionService
                address_service = AddressCollectionService(db)
                result = await address_service.handle_location_message(
                    wa_id=wa_id,
                    latitude=latitude,
                    longitude=longitude,
                    location_name=location_name,
                    location_address=location_address
                )
                
                if result["success"]:
                    # Address collection handled successfully
                    message_data = MessageCreate(
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id=to_wa_id,
                        type="location",
                        body=location_body,
                        timestamp=timestamp,
                        customer_id=customer.id,
                        latitude=latitude,
                        longitude=longitude,
                    )
                    message_service.create_message(db, message_data)
                    db.commit()  # Explicitly commit the transaction
                    
                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": to_wa_id,
                        "type": "location",
                        "latitude": latitude,
                        "longitude": longitude,
                        "timestamp": timestamp.isoformat(),
                    })
                    return {"status": "address_collected", "message_id": message_id}
                else:
                    # Fallback to old location handling
                    pass
            except Exception as e:
                print(f"Address collection location handling failed: {e}")
                # Fallback to old location handling

            # OLD LOCATION HANDLING (fallback)
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="location",
                body=location_body,
                timestamp=timestamp,
                customer_id=customer.id,
                latitude=latitude,
                longitude=longitude,
            )
            message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction

            broadcast_payload = {
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "location",
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp.isoformat()
            }

            if location_name:
                broadcast_payload["name"] = location_name
            if location_address:
                broadcast_payload["address"] = location_address

            await manager.broadcast(broadcast_payload)

            return {"status": "success", "message_id": message_id}

        elif message_type == "image":
            image = message["image"]

            media_id = image.get("id")
            caption = image.get("caption", "")
            mime_type = image.get("mime_type", "")
            filename = image.get("filename", "")

            # Save message in DB
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="image",
                body=caption or "[Image]",
                timestamp=timestamp,
                customer_id=customer.id,
                media_id=media_id,
                caption=caption,
                filename=filename,
                mime_type=mime_type,
            )
            new_msg = message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction

            # Broadcast to WebSocket clients
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "image",
                "media_id": media_id,
                "caption": caption,
                "filename": filename,
                "mime_type": mime_type,
                "timestamp": timestamp.isoformat(),
            })

            return {"status": "success", "message_id": message_id}
        elif message_type == "button":
            # Template button reply (WhatsApp sets type = "button" for template quick replies)
            btn = message.get("button", {})
            btn_text = btn.get("text", "")
            btn_id = btn.get("payload") or btn.get("id") or ""

            # Check if this is actually a flow submission disguised as a button
            # Look for flow-related data in the message
            if "flow" in str(message).lower() or "nfm" in str(message).lower():
                print(f"[ws_webhook] DEBUG - Detected flow submission in button message: {message}")
                # Process as flow submission instead of button
                try:
                    # Try to extract flow data from the message
                    flow_data = message.get("flow", {}) or message.get("nfm_reply", {})
                    if flow_data:
                        print(f"[ws_webhook] DEBUG - Processing flow data from button message: {flow_data}")
                        # Process the flow submission
                        result = await run_interactive_type(
                            db,
                            message=message,
                            interactive={"type": "nfm_reply", "nfm_reply": flow_data},
                            i_type="nfm_reply",
                            timestamp=timestamp,
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            wa_id=wa_id,
                            customer=customer,
                        )
                        if result.get("status") != "skipped":
                            return result
                except Exception as e:
                    print(f"[ws_webhook] DEBUG - Failed to process flow from button message: {e}")

            reply_text = btn_text or btn_id or "[Button Reply]"
            msg_button = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="button",
                body=reply_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, msg_button)
            db.commit()  # Explicitly commit the transaction
            
            # Optionally broadcast button click for frontend display, but avoid noise for main flows
            noisy_btn_id = (btn_id or "").lower()
            if noisy_btn_id not in {"buy_products", "book_appointment", "request_callback"}:
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": "text",
                    "message": f"🔘 {reply_text}",
                    "timestamp": timestamp.isoformat(),
                })

            # Handle different button types
            choice_text = (reply_text or "").strip().lower()

            # Buy Products from template button → trigger catalog flow immediately
            btn_id_norm = (btn_id or "").strip().lower()
            if btn_id_norm in {"buy_products", "buy product", "buy products"} or choice_text == "buy products":
                try:
                    await trigger_buy_products_from_welcome(db, wa_id=wa_id)
                except Exception:
                    pass
                return {"status": "success", "message_id": message_id}  # INSERTED: hard return (no more handlers)

            # NEW: Delegate Skin/Hair/Body and related list selections to component flow
            flow_result = await run_treatment_buttons_flow(
                db,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                message_id=message_id,
                btn_id=btn_id,
                btn_text=btn_text,
                btn_payload=(btn.get("payload") if isinstance(btn, dict) else None),
            )
            if (flow_result or {}).get("status") in {"list_sent", "hair_template_sent", "body_template_sent", "next_actions_sent"}:
                return flow_result

            # Handle template button clicks from oliva_meta_ad template
            # Map template button payloads to lead appointment flow IDs
            template_btn_mapping = {
                "yes, book now": "yes_book_appointment",
                "yes book now": "yes_book_appointment",
                "not now": "not_now",
                "not now,": "not_now",
            }
            
            # Check if this is a template button from oliva_meta_ad
            normalized_payload = (btn_text or "").strip().lower()
            mapped_id = template_btn_mapping.get(normalized_payload)
            
            if mapped_id:
                print(f"[ws_webhook] DEBUG - Template button detected: '{btn_text}' → mapped to '{mapped_id}'")
                
                # Process as lead appointment flow interactive response
                mock_interactive = {
                    "button_reply": {
                        "id": mapped_id,
                        "title": btn_text
                    }
                }
                
                # Check if user is in lead appointment flow
                try:
                    from controllers.web_socket import lead_appointment_state
                    is_in_lead_flow = wa_id in lead_appointment_state and bool(lead_appointment_state[wa_id])
                    
                    # Also check if template button (first interaction)
                    if mapped_id in {"yes_book_appointment", "not_now"}:
                        is_in_lead_flow = True
                    
                    if is_in_lead_flow or mapped_id in {"yes_book_appointment", "not_now"}:
                        print(f"[ws_webhook] DEBUG - Routing to lead appointment flow for '{mapped_id}'")
                        lead_result = await run_lead_appointment_flow(
                            db=db,
                            wa_id=wa_id,
                            message_type="interactive",
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            body_text=None,
                            timestamp=timestamp,
                            customer=customer,
                            interactive=mock_interactive,
                            i_type="button_reply",
                        )
                        if lead_result.get("status") not in {"skipped", "error"}:
                            print(f"[ws_webhook] DEBUG - Lead appointment flow handled: {lead_result.get('status')}")
                            return lead_result
                except Exception as e:
                    print(f"[ws_webhook] WARNING - Failed to process template button in lead flow: {e}")

            # Delegate appointment button flows (book, callback, time)
            from controllers.components.treament_flow import run_appointment_buttons_flow  # local import to avoid cycles
            appt_result_ctrl = await run_appointment_buttons_flow(
                db,
                wa_id=wa_id,
                btn_id=btn_id,
                btn_text=btn_text,
                btn_payload=(btn.get("payload") if isinstance(btn, dict) else None),
            )
            if (appt_result_ctrl or {}).get("status") in {"date_list_sent", "callback_ack", "appointment_captured", "need_date_first"}:
                return appt_result_ctrl

            # Address collection buttons (legacy guidance removed); allow flows to proceed without interception

            return {"status": "success", "message_id": message_id}

        elif message_type == "interactive":
            # interactive and i_type already initialized above
            print(f"[ws_webhook] DEBUG - Interactive type: {i_type}")
            if i_type == "flow":
                flow_response = interactive.get("flow_response", {})
                flow_id = flow_response.get("flow_id", "")
                print(f"[ws_webhook] DEBUG - Flow ID: {flow_id}")
                print(f"[ws_webhook] DEBUG - Flow payload: {flow_response.get('flow_action_payload', {})}")
            elif i_type == "nfm_reply":
                # Handle native flow message (new format)
                nfm_reply = interactive.get("nfm_reply", {})
                print(f"[ws_webhook] DEBUG - NFM Reply: {nfm_reply}")
                
                # Enhanced logging for debugging
                response_json = nfm_reply.get("response_json", "{}")
                print(f"[ws_webhook] DEBUG - Raw response_json: {response_json}")
                print(f"[ws_webhook] DEBUG - Response JSON length: {len(response_json)}")
                
                # Parse the response_json to extract flow data
                try:
                    response_data = json.loads(response_json)
                    print(f"[ws_webhook] DEBUG - Parsed NFM data: {response_data}")
                    print(f"[ws_webhook] DEBUG - Parsed data keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")

                    # Check if we got template variables instead of actual values
                    has_template_vars = any("{{" in str(v) and "}}" in str(v) for v in response_data.values())
                    if has_template_vars:
                        print(f"[ws_webhook] WARNING - Received template variables instead of actual values: {response_data}")
                        print(f"[ws_webhook] INFO - Processing template placeholders to extract actual values")
                        
                        # Process template placeholders and extract actual values
                        processed_data = {}
                        for key, value in response_data.items():
                            if isinstance(value, str) and "{{" in value and "}}" in value:
                                # Extract the placeholder name (e.g., "{{name}}" -> "name")
                                placeholder_match = re.search(r'\{\{([^}]+)\}\}', value)
                                if placeholder_match:
                                    placeholder_name = placeholder_match.group(1).strip()
                                    # Try to get actual value from customer data or use fallback
                                    if hasattr(customer, 'name') and customer.name and placeholder_name == 'name':
                                        processed_data[key] = customer.name
                                    elif hasattr(customer, 'wa_id') and placeholder_name == 'phone':
                                        # Use wa_id as phone fallback (remove country code if present)
                                        phone = customer.wa_id.replace('91', '') if customer.wa_id.startswith('91') else customer.wa_id
                                        processed_data[key] = phone
                                    else:
                                        # Use placeholder name as fallback value
                                        processed_data[key] = placeholder_name
                                else:
                                    processed_data[key] = value
                            else:
                                processed_data[key] = value
                        
                        print(f"[ws_webhook] INFO - Processed data from placeholders: {processed_data}")
                        response_data = processed_data

                    # Process the flow response data directly
                    # The flow fields are defined in Meta's Flow Builder, not here
                    print(f"[ws_webhook] DEBUG - Flow response data: {response_data}")
                    print(f"[ws_webhook] INFO - Flow fields received: {list(response_data.keys())}")
                    
                    # Debug each field individually
                    for key, value in response_data.items():
                        print(f"[ws_webhook] DEBUG - Field '{key}': '{value}' (type: {type(value)})")
                    
                    # No field mapping needed - use the data as received from Meta
                    # Meta's Flow Builder defines the field names and structure

                    # Validate that we have actual data
                    if not response_data or (isinstance(response_data, dict) and not any(response_data.values())):
                        print(f"[ws_webhook] WARNING - Empty or invalid response data: {response_data}")
                        await send_message_to_waid(wa_id, "❌ No data received from the form. Please try again.", db)
                        return {"status": "empty_form_data", "message_id": message_id}

                    # Convert nfm_reply to flow_response format for compatibility
                    interactive["type"] = "flow"
                    interactive["flow_response"] = {
                        "flow_id": "1314521433687006",  # Default address flow ID
                        "flow_cta": "Submit",
                        "flow_action_payload": response_data,  # Use data as received from Meta
                    }
                    i_type = "flow"  # Update type for processing
                    print(f"[ws_webhook] DEBUG - Converted to flow format, processing as flow")

                except json.JSONDecodeError as e:
                    print(f"[ws_webhook] ERROR - Invalid JSON in NFM response: {e}")
                    print(f"[ws_webhook] ERROR - Raw response_json: {response_json}")
                    await send_message_to_waid(wa_id, "❌ There was an error processing your form. Please try again.", db)
                    return {"status": "json_parse_error", "message_id": message_id}
                except Exception as e:
                    print(f"[ws_webhook] ERROR - Failed to parse NFM response: {e}")
                    print(f"[ws_webhook] ERROR - Exception type: {type(e).__name__}")
                    await send_message_to_waid(wa_id, "❌ There was an error processing your form. Please try again.", db)
                    return {"status": "parse_error", "message_id": message_id}
            # Delegate interactive handling to component
            result_interactive = await run_interactive_type(
                db,
                message=message,
                interactive=interactive,
                i_type=i_type,
                timestamp=timestamp,
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                wa_id=wa_id,
                customer=customer,
            )
            print(f"[ws_webhook] DEBUG - Interactive result: {result_interactive}")
            if (result_interactive or {}).get("status") != "skipped":
                return result_interactive
            
            # Handle other interactive types (buttons, lists)
            try:
                if i_type == "button_reply":
                    title = interactive.get("button_reply", {}).get("title")
                    reply_id = interactive.get("button_reply", {}).get("id")
                elif i_type == "list_reply":
                    title = interactive.get("list_reply", {}).get("title")
                    reply_id = interactive.get("list_reply", {}).get("id")
                else:
                    title = None
                    reply_id = None
            except Exception:
                title = None
                reply_id = None

            # NEW: Immediately persist and broadcast ANY interactive reply before branching,
            # so UI always shows the user's selection even if we return early later.
            interactive_broadcasted = False
            try:
                if i_type in {"button_reply", "list_reply"}:
                    reply_text_any = (title or reply_id or "[Interactive Reply]")
                    msg_interactive_any = MessageCreate(
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id=to_wa_id,
                        type="interactive",
                        body=reply_text_any,
                        timestamp=timestamp,
                        customer_id=customer.id,
                    )
                    message_service.create_message(db, msg_interactive_any)
                    db.commit()  # Explicitly commit the transaction
                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": to_wa_id,
                        "type": "interactive",
                        "message": reply_text_any,
                        "timestamp": timestamp.isoformat(),
                    })
                    interactive_broadcasted = True
            except Exception:
                pass

            # Step 2 → 3: If user selected Skin/Hair/Body button, save+broadcast reply, then send concerns list
            try:
                if i_type == "button_reply" and (reply_id or "").lower() in {"skin", "hair", "body"}:
                    token_entry2 = get_latest_token(db)
                    if token_entry2 and token_entry2.token:
                        access_token2 = token_entry2.token
                        headers2 = {"Authorization": f"Bearer {access_token2}", "Content-Type": "application/json"}
                        phone_id2 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                        topic = (reply_id or "").lower()
                        # If SKIN selected, trigger template skin_treat_flow (no params assumed)
                        if topic == "skin":
                            try:
                                from controllers.auto_welcome_controller import _send_template
                                lang_code_skin = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                resp_skin = _send_template(
                                    wa_id=wa_id,
                                    template_name="skin_treat_flow",
                                    access_token=token_entry2.token,
                                    phone_id=phone_id2,
                                    components=None,
                                    lang_code=lang_code_skin
                                )
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template" if resp_skin.status_code == 200 else "template_error",
                                        "message": "skin_treat_flow sent" if resp_skin.status_code == 200 else "skin_treat_flow failed",
                                        **({"status_code": resp_skin.status_code} if resp_skin.status_code != 200 else {}),
                                        **({"error": (resp_skin.text[:500] if isinstance(resp_skin.text, str) else str(resp_skin.text))} if resp_skin.status_code != 200 else {}),
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                            except Exception as e:
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template_error",
                                        "message": f"skin_treat_flow exception: {str(e)[:120]}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                        # If HAIR selected, trigger template hair_treat_flow (no params assumed) and STOP
                        elif topic == "hair":
                            try:
                                from controllers.auto_welcome_controller import _send_template
                                lang_code_hair = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                resp_hair = _send_template(
                                    wa_id=wa_id,
                                    template_name="hair_treat_flow",
                                    access_token=token_entry2.token,
                                    phone_id=phone_id2,
                                    components=None,
                                    lang_code=lang_code_hair
                                )
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template" if resp_hair.status_code == 200 else "template_error",
                                        "message": "hair_treat_flow sent" if resp_hair.status_code == 200 else "hair_treat_flow failed",
                                        **({"status_code": resp_hair.status_code} if resp_hair.status_code != 200 else {}),
                                        **({"error": (resp_hair.text[:500] if isinstance(resp_hair.text, str) else str(resp_hair.text))} if resp_hair.status_code != 200 else {}),
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                                # Do not send any further lists or flows for hair; exit early
                                return {"status": "hair_template_sent", "message_id": message_id}
                            except Exception as e:
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template_error",
                                        "message": f"hair_treat_flow exception: {str(e)[:120]}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                        def list_rows(items):
                            return [{"id": f"{topic}:{i}", "title": title} for i, title in enumerate(items, start=1)]

                        if topic == "skin":
                            # Send exactly as requested for Skin: custom ids and labels, no header
                            payload_list = {
                                "messaging_product": "whatsapp",
                                "to": wa_id,
                                "type": "interactive",
                                "interactive": {
                                    "type": "list",
                                    "body": {"text": "Please select your Skin concern:"},
                                    "action": {
                                        "button": "Select Concern",
                                        "sections": [
                                            {
                                                "title": "Skin Concerns",
                                                "rows": [
                                                    {"id": "acne", "title": "Acne / Acne Scars"},
                                                    {"id": "pigmentation", "title": "Pigmentation & Uneven Skin Tone"},
                                                    {"id": "antiaging", "title": "Anti-Aging & Skin Rejuvenation"},
                                                    {"id": "laser", "title": "Laser Hair Removal"},
                                                    {"id": "other_skin", "title": "Other Skin Concerns"}
                                                ]
                                            }
                                        ]
                                    }
                                }
                            }
                            # Send to WA API
                            requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                            # Broadcast to ChatWindow so the UI shows the outgoing list
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "interactive",
                                    "message": "Please select your Skin concern:",
                                    "timestamp": datetime.now().isoformat(),
                                    "meta": {"kind": "list", "section": "Skin Concerns"}
                                })
                            except Exception:
                                pass
                            return {"status": "list_sent", "message_id": message_id}
                        elif topic == "hair":
                            rows = list_rows(["Hair Loss / Hair Fall", "Hair Transplant", "Dandruff & Scalp Care", "Other Hair Concerns"])
                            section_title = "Hair"
                        else:
                            # If BODY selected, trigger template body_treat_flow (no params) and STOP
                            if topic == "body":
                                try:
                                    from controllers.auto_welcome_controller import _send_template
                                    lang_code_body = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                    resp_body = _send_template(
                                        wa_id=wa_id,
                                        template_name="body_treat_flow",
                                        access_token=token_entry2.token,
                                        phone_id=phone_id2,
                                        components=None,
                                        lang_code=lang_code_body
                                    )
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "template" if resp_body.status_code == 200 else "template_error",
                                            "message": "body_treat_flow sent" if resp_body.status_code == 200 else "body_treat_flow failed",
                                            **({"status_code": resp_body.status_code} if resp_body.status_code != 200 else {}),
                                            **({"error": (resp_body.text[:500] if isinstance(resp_body.text, str) else str(resp_body.text))} if resp_body.status_code != 200 else {}),
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    except Exception:
                                        pass
                                    return {"status": "body_template_sent", "message_id": message_id}
                                except Exception as e:
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "template_error",
                                            "message": f"body_treat_flow exception: {str(e)[:120]}",
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    except Exception:
                                        pass
                            rows = list_rows(["Weight Management", "Body Contouring", "Weight Loss", "Other Body Concerns"])
                            section_title = "Body"

                      
                        # Send to WhatsApp API
                        requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                        # Broadcast to ChatWindow so the UI shows the outgoing list
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "interactive",
                                "message": f"Please select your {section_title} concern:",
                                "timestamp": datetime.now().isoformat(),
                                "meta": {"kind": "list", "section": section_title}
                            })
                        except Exception:
                            pass
                        return {"status": "list_sent", "message_id": message_id}
            except Exception:
                pass

            # Follow-Up 1: User tapped Yes → trigger welcome and confirmation flow
            try:
                if i_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = (button_reply.get("id", "") or "").strip().lower()
                    if button_id == "followup_yes":
                        # Clear any pending follow-up timers and reset state so new inactivity starts with Follow-Up 1
                        try:
                            from services.followup_service import mark_customer_replied as _mark_replied
                            _mark_replied(db, customer_id=customer.id)
                        except Exception:
                            pass
                        from services.whatsapp_service import get_latest_token as _get_token
                        token_entry2 = _get_token(db)
                        if token_entry2 and token_entry2.token:
                            access_token2 = token_entry2.token
                            phone_id2 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                            lang_code2 = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                            # Send mr_welcome template
                            from controllers.auto_welcome_controller import _send_template as _send_tpl
                            body_components2 = [{
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": (sender_name or wa_id or "there")}
                                ]
                            }]
                            _send_tpl(
                                wa_id=wa_id,
                                template_name="mr_welcome",
                                access_token=access_token2,
                                phone_id=phone_id2,
                                components=body_components2,
                                lang_code=lang_code2,
                            )

                            # Schedule follow-up only for mr_welcome
                            try:
                                from services.followup_service import schedule_next_followup as _schedule
                                _schedule(db, customer_id=customer.id, delay_minutes=2, stage_label="mr_welcome_sent")
                            except Exception:
                                pass

                            # Send name/phone confirmation prompt
                            try:
                                from services.customer_service import get_customer_record_by_wa_id
                                customer_rec = get_customer_record_by_wa_id(db, wa_id)
                                display_name = (customer_rec.name.strip() if customer_rec and isinstance(customer_rec.name, str) else None) or "there"
                                import re as _re
                                digits = _re.sub(r"\D", "", wa_id)
                                last10 = digits[-10:] if len(digits) >= 10 else None
                                display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
                            except Exception:
                                display_name = "there"
                                display_phone = wa_id

                            from utils.whatsapp import send_message_to_waid as _send_text
                            await _send_text(wa_id, f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*", db)

                            # Send Yes/No buttons for confirmation
                            token_entry_btn = _get_token(db)
                            if token_entry_btn and token_entry_btn.token:
                                access_token_btn = token_entry_btn.token
                                phone_id_btn = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                                headers_btn = {"Authorization": f"Bearer {access_token_btn}", "Content-Type": "application/json"}
                                payload_btn = {
                                    "messaging_product": "whatsapp",
                                    "to": wa_id,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button",
                                        "body": {"text": "Are your name and contact number correct? "},
                                        "action": {
                                            "buttons": [
                                                {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes"}},
                                                {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}},
                                            ]
                                        },
                                    },
                                }
                                requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                        return {"status": "followup_yes_flow_started", "message_id": message_id}
            except Exception:
                pass

            # Appointment booking entry shortcuts
            try:
                if i_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = button_reply.get("id", "")
                    button_title = button_reply.get("title", "")
                    
                    # Book Appointment is now fully handled inside controllers.components.interactive_type.run_interactive_type
                    
                    if ((button_id or "").lower() == "request_callback" or 
                        (button_title or "").strip().lower() == "request a call back"):
                        await send_message_to_waid(wa_id, "📌 Thank you for your interest! One of our team members will contact you shortly to assist further.", db)
                        return {"status": "callback_ack", "message_id": message_id}
            except Exception:
                pass

            # Date picked from list
            try:
                if i_type == "list_reply" and (reply_id or "").lower().startswith("date_"):
                    date_iso = (reply_id or "")[5:]
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
                        appointment_state[wa_id] = {"date": date_iso}
                        await send_message_to_waid(wa_id, f"✅ Date selected: {date_iso}", db)
                        await send_time_buttons(wa_id, db)
                        return {"status": "date_selected", "message_id": message_id}
            except Exception:
                pass

            # Time picked from button reply (interactive path)
            try:
                if i_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = button_reply.get("id", "")
                    button_title = button_reply.get("title", "")
                    
                    if ((button_id or "").lower().startswith("time_") or 
                        (button_title or "").strip() in ["10:00 AM", "2:00 PM", "6:00 PM"]):
                        time_map = {
                            "time_10_00": "10:00 AM",
                            "time_14_00": "2:00 PM", 
                            "time_18_00": "6:00 PM",
                        }
                        time_label = (time_map.get((button_id or "").lower()) or 
                                    (button_title or "").strip())
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        if date_iso and time_label:
                            await _confirm_appointment(wa_id, db, date_iso, time_label)
                            return {"status": "appointment_captured", "message_id": message_id}
                    # Handle Yes/No confirmation for name/phone (accept common ids/titles)
                    norm_btn_id = (button_id or "").strip().lower()
                    norm_btn_title = (button_title or "").strip().lower()
                    yes_ids = {"confirm_yes", "yes", "y", "ok", "confirm"}
                    no_ids = {"confirm_no", "no", "n", "incorrect"}
                    if norm_btn_id in yes_ids or norm_btn_title in yes_ids or norm_btn_id in no_ids or norm_btn_title in no_ids:
                        # Retrieve stored date/time
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        time_label = (appointment_state.get(wa_id) or {}).get("time")
                        try:
                            from services.customer_service import get_customer_record_by_wa_id
                            customer = get_customer_record_by_wa_id(db, wa_id)
                            display_name = (customer.name.strip() if customer and isinstance(customer.name, str) else None) or "there"
                        except Exception:
                            display_name = "there"
                        # Derive phone from wa_id
                        try:
                            import re as _re
                            digits = _re.sub(r"\D", "", wa_id)
                            last10 = digits[-10:] if len(digits) >= 10 else None
                            display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
                        except Exception:
                            display_phone = wa_id

                        # Check if this is from treatment flow
                        st = appointment_state.get(wa_id) or {}
                        from_treatment_flow = st.get("from_treatment_flow", False)
                        
                        if (norm_btn_id in yes_ids or norm_btn_title in yes_ids):
                            if from_treatment_flow:
                                try:
                                    from controllers.components.lead_appointment_flow.city_selection import send_city_selection  # type: ignore
                                    result = await send_city_selection(db, wa_id=wa_id)
                                    return {"status": "proceed_to_city_selection", "message_id": message_id, "result": result}
                                except Exception as e:
                                    print(f"[treatment_flow] WARNING - Could not send city selection: {e}")
                                    return {"status": "failed", "message_id": message_id}
                            elif date_iso and time_label:
                                
                                # Regular appointment flow with date/time
                                thank_you = (
                                f"✅ Thank you! Your preferred appointment is on {date_iso} at {time_label} with {display_name} ({display_phone}). "
                                f"Your appointment is booked, and our team will call to confirm shortly."
                            )
                            # Persist appointment details to DB (create additional record for same wa_id)
                            try:
                                from services.referrer_service import referrer_service
                                existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                existing_treat = getattr(existing_ref, 'treatment_type', None) if existing_ref else ''
                                # Create a new appointment row (allow multiple per wa_id)
                                referrer_service.create_appointment_booking(
                                    db,
                                    wa_id,
                                    date_iso,
                                    time_label,
                                    existing_treat or ''
                                )
                            except Exception:
                                pass
                            await send_message_to_waid(wa_id, thank_you, db)
                            # Now clear state
                            try:
                                if wa_id in appointment_state:
                                    appointment_state.pop(wa_id, None)
                            except Exception:
                                pass
                            return {"status": "appointment_confirmed", "message_id": message_id}
                        elif (norm_btn_id in no_ids or norm_btn_title in no_ids):
                            # Ask for name first, then number (validated via OpenAI-backed validators)
                            try:
                                st = appointment_state.get(wa_id) or {}
                                # Try to recover date/time from DB if missing
                                if not st.get("date") or not st.get("time"):
                                    try:
                                        from services.referrer_service import referrer_service
                                        existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                        if existing_ref and getattr(existing_ref, "appointment_date", None) and getattr(existing_ref, "appointment_time", None):
                                            try:
                                                date_iso_rec = getattr(existing_ref.appointment_date, "date", None)()
                                                st["date"] = date_iso_rec.isoformat()
                                            except Exception:
                                                try:
                                                    st["date"] = existing_ref.appointment_date.strftime("%Y-%m-%d")
                                                except Exception:
                                                    pass
                                            st["time"] = existing_ref.appointment_time
                                    except Exception:
                                        pass
                                st["awaiting_name"] = True
                                st.pop("awaiting_phone", None)
                                st.pop("corrected_name", None)
                                st.pop("corrected_phone", None)
                                appointment_state[wa_id] = st
                            except Exception:
                                pass
                            await send_message_to_waid(wa_id, "No problem. Let's update your details.\nPlease share your full name first.", db)
                            return {"status": "awaiting_name", "message_id": message_id}
                        else:
                            # Before sending user back, try to recover any existing appointment from DB
                            try:
                                from services.referrer_service import referrer_service
                                existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                if existing_ref and getattr(existing_ref, "appointment_date", None) and getattr(existing_ref, "appointment_time", None):
                                    st = appointment_state.get(wa_id) or {}
                                    try:
                                        date_iso_rec = getattr(existing_ref.appointment_date, "date", None)()
                                        st["date"] = date_iso_rec.isoformat()
                                    except Exception:
                                        try:
                                            st["date"] = existing_ref.appointment_date.strftime("%Y-%m-%d")
                                        except Exception:
                                            pass
                                    st["time"] = existing_ref.appointment_time
                                    appointment_state[wa_id] = st
                                    # If we recovered date/time and the user had pressed Yes earlier, confirm now
                                    if norm_btn_id in yes_ids or norm_btn_title in yes_ids:
                                        await _confirm_appointment(wa_id, db, st.get("date"), st.get("time"))
                                        return {"status": "appointment_captured", "message_id": message_id}
                                    # If it was not an explicit Yes, at least proceed to name capture without resetting flow
                                    await send_message_to_waid(wa_id, "No problem. Let's update your details.\nPlease share your full name first.", db)
                                    st["awaiting_name"] = True
                                    appointment_state[wa_id] = st
                                    return {"status": "awaiting_name", "message_id": message_id}
                            except Exception:
                                pass
                            # Fallback: ask to pick week/date
                            await send_message_to_waid(wa_id, "Please select a week and then a date.", db)
                            try:
                                from controllers.components.interactive_type import send_week_list  # type: ignore
                                await send_week_list(db, wa_id)
                            except Exception:
                                pass
                            return {"status": "need_date_first", "message_id": message_id}
            except Exception:
                pass

            # (Removed) Plain text YES/NO confirmations inside interactive branch to avoid duplication

            # Step 3 → 6: After a list selection, save+broadcast reply, then present next-step action buttons
            try:
                if (i_type in {"list_reply", "button_reply"}) and (reply_id or title):
                    # Store selected concern/treatment for later mapping to Zoho
                    # Prefer visible title; if only an ID is present, map to canonical title
                    selected_concern = title or reply_id or ""
                    # Normalize a few known IDs to display titles when Meta sends only IDs
                    # Normalize: prefer the exact title text when present
                    # If only an ID comes, translate to a canonical title once.
                    id_to_title_map = {
                        "acne": "Acne / Acne Scars",
                        "pigmentation": "Pigmentation & Uneven Skin Tone",
                        "antiaging": "Anti-Aging & Skin Rejuvenation",
                        "dandruff": "Dandruff & Scalp Care",
                        "other_skin": "Other Skin Concerns",
                        "hair_loss": "Hair Loss / Hair Fall",
                        "hair_transplant": "Hair Transplant",
                        "other_hair": "Other Hair Concerns",
                        "weight_mgmt": "Weight Management",
                        "body_contouring": "Body Contouring",
                        "other_body": "Other Body Concerns",
                    }
                    if (not title) and (reply_id or "").lower() in id_to_title_map:
                        selected_concern = id_to_title_map[(reply_id or "").lower()]
                    # Fallback for button payload structure
                    if not selected_concern:
                        try:
                            btn = (interactive or {}).get("button", {})
                            btn_text = btn.get("text") or btn.get("payload")
                            if btn_text:
                                selected_concern = btn_text
                        except Exception:
                            pass
                    # Canonicalize common variants (e.g., 'Skin: Acne' -> 'Acne / Acne Scars')
                    try:
                        def _canon(txt: str) -> str:
                            import re as _re
                            return _re.sub(r"[^a-z0-9]+", " ", (txt or "").lower()).strip()
                        raw = (selected_concern or "").strip()
                        # Remove optional category prefixes like "Skin: ", "Hair: ", "Body: "
                        for cat_prefix in ["skin:", "hair:", "body:"]:
                            if raw.lower().startswith(cat_prefix):
                                raw = raw[len(cat_prefix):].strip()
                        canon = _canon(raw)
                        synonyms_to_canonical = {
                            "acne": "Acne / Acne Scars",
                            "acne acne scars": "Acne / Acne Scars",
                            "pigmentation": "Pigmentation & Uneven Skin Tone",
                            "uneven skin tone": "Pigmentation & Uneven Skin Tone",
                            "anti aging": "Anti-Aging & Skin Rejuvenation",
                            "skin rejuvenation": "Anti-Aging & Skin Rejuvenation",
                            "dandruff": "Dandruff & Scalp Care",
                            "dandruff scalp care": "Dandruff & Scalp Care",
                            "laser hair removal": "Laser Hair Removal",
                            "hair loss hair fall": "Hair Loss / Hair Fall",
                            "hair transplant": "Hair Transplant",
                            "weight management": "Weight Management",
                            "body contouring": "Body Contouring",
                            "weight loss": "Weight Loss",
                            "other skin concerns": "Other Skin Concerns",
                            "other hair concerns": "Other Hair Concerns",
                            "other body concerns": "Other Body Concerns",
                        }
                        if canon in synonyms_to_canonical:
                            selected_concern = synonyms_to_canonical[canon]
                    except Exception:
                        pass

                    if selected_concern:
                        try:
                            if wa_id not in appointment_state:
                                appointment_state[wa_id] = {}
                            appointment_state[wa_id]["selected_concern"] = selected_concern
                            print(f"[treatment_flow] DEBUG - Stored selected concern: {selected_concern} (reply_id={reply_id}, title={title})")
                            # Also mirror into lead_appointment_state as fallback source
                            try:
                                if wa_id not in lead_appointment_state:
                                    lead_appointment_state[wa_id] = {}
                                lead_appointment_state[wa_id]["selected_concern"] = selected_concern
                                print(f"[lead_appointment_flow] DEBUG - Mirrored selected concern to lead_appointment_state: {selected_concern}")
                            except Exception as e:
                                print(f"[lead_appointment_flow] WARNING - Could not mirror selected concern: {e}")
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Could not store selected concern: {e}")
                    
                    # Do NOT rebroadcast here; unified early broadcast already did it.
                    # Trigger booking_appoint template right after treatment selection
                    try:
                        token_entry_book = get_latest_token(db)
                        if token_entry_book and token_entry_book.token:
                            phone_id_book = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                            lang_code_book = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                            from controllers.auto_welcome_controller import _send_template
                            resp_book = _send_template(
                                wa_id=wa_id,
                                template_name="booking_appoint",
                                access_token=token_entry_book.token,
                                phone_id=phone_id_book,
                                components=None,
                                lang_code=lang_code_book
                            )
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template" if resp_book.status_code == 200 else "template_error",
                                    "message": "booking_appoint sent" if resp_book.status_code == 200 else "booking_appoint failed",
                                    **({"status_code": resp_book.status_code} if resp_book.status_code != 200 else {}),
                                    **({"error": (resp_book.text[:500] if isinstance(resp_book.text, str) else str(resp_book.text))} if resp_book.status_code != 200 else {}),
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception:
                                pass
                    except Exception:
                        pass

                    token_entry3 = get_latest_token(db)
                    if token_entry3 and token_entry3.token:
                        access_token3 = token_entry3.token
                        headers3 = {"Authorization": f"Bearer {access_token3}", "Content-Type": "application/json"}
                        phone_id3 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                        payload_buttons = {
                            "messaging_product": "whatsapp",
                            "to": wa_id,
                            "type": "interactive",
                            "interactive": {
                                "type": "button",
                                "body": {"text": "Please choose one of the following options:"},
                                "action": {
                                    "buttons": [
                                        {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 📅 Book an Appointment"}},
                                        {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde 📞 Request a Call Back"}}
                                    ]
                                }
                            }
                        }
                        # Broadcast first so UI shows event even if WA API fails
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "interactive",
                                "message": "Please choose one of the following options:",
                                "timestamp": timestamp.isoformat(),
                                "meta": {"kind": "buttons", "options": ["📅 Book an Appointment", "📞 Request a Call Back"]}
                            })
                        except Exception:
                            pass
                        # Then attempt to send to WhatsApp API
                        requests.post(get_messages_url(phone_id3), headers=headers3, json=payload_buttons)
                        return {"status": "next_actions_sent", "message_id": message_id}
            except Exception:
                pass

            # Save and broadcast interactive reply only if we didn't already do it above
            if not interactive_broadcasted:
                reply_text = title or reply_id or "[Interactive Reply]"
                msg_interactive = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type="interactive",
                    body=reply_text,
                    timestamp=timestamp,
                    customer_id=customer.id,
                )
                # Save only; avoid second broadcast to prevent duplicates
                message_service.create_message(db, msg_interactive)
                db.commit()  # Explicitly commit the transaction

            # If user chose Buy Products → send only the WhatsApp catalog link (strict match)
            try:
                reply_text  # may be undefined if we already broadcast earlier
            except NameError:
                reply_text = title or reply_id or ""
            choice_text = (reply_text or "").strip().lower()
            if (reply_id and reply_id.lower() == "buy_products") or (choice_text == "buy products"):
                try:
                    await trigger_buy_products_from_welcome(db, wa_id=wa_id)
                except Exception:
                    pass
            return {"status": "success", "message_id": message_id}
        elif message_type == "document":
            document = message["document"]

            media_id = document.get("id")
            caption = document.get("caption", "")
            mime_type = document.get("mime_type", "")
            filename = document.get("filename", "")

            # Save document message in DB
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="document",
                body=caption or "[Document]",
                timestamp=timestamp,
                customer_id=customer.id,
                media_id=media_id,
                caption=caption,
                filename=filename,
                mime_type=mime_type,
            )
            new_msg = message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction

            # Broadcast to WebSocket clients
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "document",
                "media_id": media_id,
                "caption": caption,
                "filename": filename,
                "mime_type": mime_type,
                "timestamp": timestamp.isoformat(),
            })

            return {"status": "success", "message_id": message_id}
        
        # Handle free-form text in treatment flow to capture name/phone even if user skips buttons
        # BUT: Only validate if message looks like name/phone input, not conversational text
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                if bool(st.get("from_treatment_flow")) and not bool(st.get("awaiting_name")) and not bool(st.get("awaiting_phone")):
                    # Check if message is conversational (contains common conversational phrases)
                    # If so, skip validation - user should use Yes/No buttons instead
                    conversational_indicators = [
                        "thanks", "thank", "hi", "hello", "hey", "please", "share", 
                        "your", "number", "want", "now", "need", "help", "ok", "okay"
                    ]
                    text_lower = body_text.lower()
                    is_conversational = any(indicator in text_lower for indicator in conversational_indicators) and len(body_text.split()) > 5
                    
                    # Also check if it's clearly a request/question rather than name/phone input
                    is_request = any(word in text_lower for word in ["share", "provide", "give", "send", "tell"])
                    
                    # Skip validation if message is clearly conversational or a request
                    if is_conversational or is_request:
                        # User is likely responding conversationally to Yes/No buttons
                        # Don't validate as name/phone, let the normal flow handle it
                        pass
                    else:
                        # Only validate if message looks like it might be name/phone input
                        # Must be relatively short and not contain request words
                        name_res = validate_human_name(body_text)
                        phone_res = validate_indian_phone(body_text)
                        name_ok = bool(name_res.get("valid")) and bool(name_res.get("name"))
                        phone_ok = bool(phone_res.get("valid")) and bool(phone_res.get("phone"))
                        if name_ok and phone_ok:
                            st["corrected_name"] = name_res.get("name").strip()
                            st["corrected_phone"] = phone_res.get("phone")
                            st["awaiting_name"] = False
                            st["awaiting_phone"] = False
                            appointment_state[wa_id] = st
                            # Update local customer record with corrected details
                            try:
                                from services.customer_service import get_customer_record_by_wa_id, update_customer
                                from schemas.customer_schema import CustomerUpdate
                                cust = get_customer_record_by_wa_id(db, wa_id)
                                if cust:
                                    # Normalize WA number to +91XXXXXXXXXX
                                    import re as _re
                                    wa_digits = _re.sub(r"\D", "", wa_id)
                                    wa_last10 = wa_digits[-10:] if len(wa_digits) >= 10 else wa_digits
                                    wa_norm = ("+91" + wa_last10) if len(wa_last10) == 10 else wa_id
                                update_customer(db, cust.id, CustomerUpdate(
                                    name=name_res.get("name").strip(),
                                    phone_2=phone_res.get("phone"),
                                ))
                            except Exception:
                                pass
                            # After capturing both, go to city selection
                            try:
                                from controllers.components.lead_appointment_flow.city_selection import send_city_selection  # type: ignore
                                result = await send_city_selection(db, wa_id=wa_id)
                                return {"status": "proceed_to_city_selection", "message_id": message_id, "result": result}
                            except Exception:
                                return {"status": "failed_after_details", "message_id": message_id}
                        elif name_ok and not phone_ok:
                            # Only set awaiting_phone if the extracted name seems valid AND message is short (likely just a name)
                            # Don't trigger if message is long/conversational
                            if len(body_text.strip().split()) <= 5:
                                st["corrected_name"] = name_res.get("name").strip()
                                st["awaiting_name"] = False
                                st["awaiting_phone"] = True
                                appointment_state[wa_id] = st
                                await send_message_to_waid(wa_id, f"Thanks {st['corrected_name']}! Now please share your number.", db)
                                return {"status": "name_captured_awaiting_phone", "message_id": message_id}
                        elif phone_ok and not name_ok:
                            # Only set awaiting_name if the extracted phone seems valid AND message is short
                            if len(body_text.strip().split()) <= 5:
                                st["corrected_phone"] = phone_res.get("phone")
                                st["awaiting_name"] = True
                                st["awaiting_phone"] = False
                                appointment_state[wa_id] = st
                                await send_message_to_waid(wa_id, "Got your number. Please share your name (full name or first name).", db)
                                return {"status": "phone_captured_awaiting_name", "message_id": message_id}
        except Exception:
            pass
        
        # Handle text while awaiting_name using OpenAI-backed validator
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                if bool(st.get("awaiting_name")):
                    # Check if message is conversational (not a name input)
                    conversational_indicators = [
                        "thanks", "thank", "hi", "hello", "hey", "please", "share", 
                        "your", "number", "want", "now", "need", "help", "ok", "okay"
                    ]
                    text_lower = body_text.lower()
                    is_conversational = any(indicator in text_lower for indicator in conversational_indicators) and len(body_text.split()) > 5
                    is_request = any(word in text_lower for word in ["share", "provide", "give", "send", "tell"])
                    
                    # Skip validation if message is clearly conversational or a request
                    if is_conversational or is_request:
                        # User is responding conversationally, not providing a name
                        # Don't validate - this shouldn't happen if awaiting_name is correctly set,
                        # but if it does, just skip validation to avoid incorrect error messages
                        pass
                    else:
                        result = validate_human_name(body_text)
                        if result.get("valid") and result.get("name"):
                            # Save corrected name and clear awaiting_name; ask for phone next
                            st["corrected_name"] = result.get("name").strip()
                            st["awaiting_name"] = False
                            st["awaiting_phone"] = True
                            appointment_state[wa_id] = st
                            await send_message_to_waid(wa_id, f"Thanks {st['corrected_name']}! Now please share your number.", db)
                            return {"status": "name_captured_awaiting_phone", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ That doesn't look like a valid name. Please send your full name or first name (letters only).", db)
                            return {"status": "invalid_name", "message_id": message_id}
        except Exception:
            pass

        # Handle text while awaiting_phone using validator
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                if bool(st.get("awaiting_phone")):
                    phone_res = validate_indian_phone(body_text)
                    if phone_res.get("valid") and phone_res.get("phone"):
                        st["corrected_phone"] = phone_res.get("phone")
                        st["awaiting_phone"] = False
                        appointment_state[wa_id] = st
                        # Build final confirmation message with date/time and updated name/number
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        time_label = (appointment_state.get(wa_id) or {}).get("time")
                        name_final = (st.get("corrected_name") or "there").strip()
                        phone_final = st.get("corrected_phone")
                        from_treatment_flow = st.get("from_treatment_flow", False)
                        
                        if from_treatment_flow and name_final and phone_final:
                            # Update local customer record with corrected details
                            try:
                                from services.customer_service import get_customer_record_by_wa_id, update_customer
                                from schemas.customer_schema import CustomerUpdate
                                import re as _re
                                cust = get_customer_record_by_wa_id(db, wa_id)
                                if cust:
                                    wa_digits = _re.sub(r"\D", "", wa_id)
                                    wa_last10 = wa_digits[-10:] if len(wa_digits) >= 10 else wa_digits
                                    wa_norm = ("+91" + wa_last10) if len(wa_last10) == 10 else wa_id
                                    update_customer(db, cust.id, CustomerUpdate(name=name_final, phone_2=phone_final))
                            except Exception:
                                pass
                            # After capturing both, go to city selection
                            try:
                                from controllers.components.lead_appointment_flow.city_selection import send_city_selection  # type: ignore
                                result = await send_city_selection(db, wa_id=wa_id)
                                return {"status": "proceed_to_city_selection", "message_id": message_id, "result": result}
                            except Exception:
                                return {"status": "failed_after_details", "message_id": message_id}
                        elif date_iso and time_label and name_final and phone_final:
                            # Regular appointment flow with date/time
                            msg = (
                                f"✅ Thank you! Your preferred appointment is on {date_iso} at {time_label} "
                                f"with {name_final} ({phone_final}). Your appointment is booked, and our team will call to confirm shortly."
                            )
                            # Persist appointment details to DB (create additional record for same wa_id)
                            try:
                                from services.referrer_service import referrer_service
                                existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                existing_treat = getattr(existing_ref, 'treatment_type', None) if existing_ref else ''
                                # Create a new appointment row (allow multiple per wa_id)
                                referrer_service.create_appointment_booking(
                                    db,
                                    wa_id,
                                    date_iso,
                                    time_label,
                                    existing_treat or ''
                                )
                            except Exception:
                                pass
                            await send_message_to_waid(wa_id, msg, db)
                            # Clear state after confirmation
                            try:
                                if wa_id in appointment_state:
                                    appointment_state.pop(wa_id, None)
                            except Exception:
                                pass
                            return {"status": "appointment_confirmed_after_details", "message_id": message_id}
                        else:
                            # Date/time should exist at this point (user tapped No on confirm).
                            # If somehow missing, prompt user to pick date again.
                            await send_message_to_waid(wa_id, "Please select a week and then a date.", db)
                            try:
                                from controllers.components.interactive_type import send_week_list  # type: ignore
                                await send_week_list(db, wa_id)
                            except Exception:
                                pass
                            return {"status": "need_date_first", "message_id": message_id}
                    else:
                        await send_message_to_waid(wa_id, "❌ That doesn't look like a valid Indian mobile number. Please send exactly 10 digits (or +91XXXXXXXXXX).", db)
                        return {"status": "invalid_phone", "message_id": message_id}
        except Exception:
            pass

        if message_type != "text":
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type=message_type,
                body=body_text,
                timestamp=timestamp,
                customer_id=customer.id
            )
            message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": message_type,
                "message": message_data.body,
                "timestamp": message_data.timestamp.isoformat()
            })

        return {"status": "success", "message_id": message_id}

    except KeyError as e:
        print(f"Webhook error: Missing key in webhook payload - {e}")
        print("This might be a status update webhook that should be skipped")
        import traceback
        print(traceback.format_exc())
        return {"status": "ignored", "message": f"Missing key: {e}"}
    except Exception as e:
        print("Webhook error:", e)
        import traceback
        print(traceback.format_exc())
        return {"status": "failed", "error": str(e)}

@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        # implement the database insertion logic here and complete this function
        return PlainTextResponse(content=challenge)
    else:
          raise HTTPException(status_code=403)