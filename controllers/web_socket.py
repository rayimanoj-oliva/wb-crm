from datetime import datetime, timedelta
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List
import re
import mimetypes
import asyncio
import os
import json
import requests

from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from schemas.orders_schema import OrderItemCreate,OrderCreate, PaymentCreate
from services import customer_service, message_service, order_service
from services import payment_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url, get_media_url
from utils.razorpay_utils import create_razorpay_payment_link
from utils.ws_manager import manager
from utils.shopify_admin import update_variant_price
from utils.address_validator import analyze_address, format_errors_for_user

router = APIRouter()


# In-memory store: { wa_id: True/False }
awaiting_address_users = {}
# Track whether we've already nudged the user to use the form to avoid repeats
address_nudge_sent = {}

# In-memory appointment scheduling state per user
# Structure: { wa_id: { "date": "YYYY-MM-DD" } }
appointment_state = {}


# WebSocket endpoint
@router.websocket("/channel")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keeping connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

VERIFY_TOKEN = "Oliva@123"

async def send_address_form(wa_id: str, db: Session):
    """Send structured address collection form similar to JioMart"""
    try:
        # Get WhatsApp token
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address form. Please try again.", db)
            return
        
        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
        
        # Create interactive form for address collection (using buttons as fallback)
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "📍 New Address"
                },
                "body": {
                    "text": "Please choose how you'd like to add your address:"
                },
                "footer": {
                    "text": "All fields are required for delivery"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "fill_form_step1",
                                "title": "📝 Fill Address Form"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "share_location",
                                "title": "📍 Share Location"
                            }
                        }
                    ]
                }
            }
        }
        
        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                form_msg_id = resp.json()["messages"][0]["id"]
                form_message = MessageCreate(
                    message_id=form_msg_id,
                    from_wa_id="917729992376",  # Your WhatsApp number
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Address collection form sent",
                    timestamp=datetime.now(),
                    customer_id=customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="")).id
                )
                message_service.create_message(db, form_message)
                
                await manager.broadcast({
                    "from": "917729992376",
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address collection form sent",
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                print(f"Error saving address form message: {e}")
        else:
            print(f"Failed to send address form: {resp.text}")
            # Fallback to simple text form
            await send_message_to_waid(wa_id, "📝 Please enter your address in this format:", db)
            await send_message_to_waid(wa_id, 
                """*Contact Details:*
Full Name: [Your Name]
Phone: [10-digit number]

*Address Details:*
Pincode: [6-digit pincode]
House No. & Street: [House number and street]
Area/Locality: [Your area]
City: [Your city]
State: [Your state]
Landmark: [Optional - nearby landmark]""", db)
            
    except Exception as e:
        print(f"Error sending address form: {e}")
        # Fallback to simple text form
        await send_message_to_waid(wa_id, "📝 Please enter your address in this format:", db)
        await send_message_to_waid(wa_id, 
            """*Contact Details:*
Full Name: [Your Name]
Phone: [10-digit number]

*Address Details:*
Pincode: [6-digit pincode]
House No. & Street: [House number and street]
Area/Locality: [Your area]
City: [Your city]
State: [Your state]
Landmark: [Optional - nearby landmark]""", db)


async def send_address_flow_button(wa_id: str, db: Session, customer_name: str = "Customer"):
    """Send WhatsApp Flow button for address collection"""
    try:
        # Get WhatsApp token
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address flow. Please try again.", db)
            return
        
        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
        
        # Import the flow template
        from utils.address_templates import get_address_collection_flow_template
        
        # Get the flow payload
        payload = get_address_collection_flow_template(wa_id, customer_name)
        
        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                flow_msg_id = resp.json()["messages"][0]["id"]
                flow_message = MessageCreate(
                    message_id=flow_msg_id,
                    from_wa_id="917729992376",  # Your WhatsApp number
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Address collection flow sent",
                    timestamp=datetime.now(),
                    customer_id=customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="")).id
                )
                message_service.create_message(db, flow_message)
                
                await manager.broadcast({
                    "from": "917729992376",
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address collection flow sent",
                    "timestamp": datetime.now().isoformat()
                })
                
                print(f"Address flow button sent successfully: {flow_msg_id}")
                
            except Exception as e:
                print(f"Error saving address flow message: {e}")
        else:
            print(f"Failed to send address flow: {resp.text}")
            # Fallback to regular form
            await send_address_form(wa_id, db)
            
    except Exception as e:
        print(f"Error sending address flow: {e}")
        # Fallback to regular form
        await send_address_form(wa_id, db)


def _generate_next_dates(num_days: int = 7):
    try:
        today = datetime.now()
        rows = []
        for i in range(num_days):
            d = today + timedelta(days=i + 1)
            date_id = d.strftime("date_%Y-%m-%d")
            title = d.strftime("%d %b %Y (%A)")
            rows.append({"id": date_id, "title": title})
        return rows
    except Exception:
        return []


async def send_date_list(wa_id: str, db: Session, header_text: str | None = None):
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to fetch appointment dates right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_next_dates(7)
        if not rows:
            await send_message_to_waid(wa_id, "❌ No dates available. Please try again later.", db)
            return {"success": False}

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                **({"header": {"type": "text", "text": header_text}} if header_text else {}),
                "body": {"text": "Please select your preferred appointment date \ud83d\udcc5"},
                "action": {
                    "button": "Choose Date",
                    "sections": [
                        {"title": "Available Dates", "rows": rows}
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
                    "message": "Please select your preferred appointment date",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Dates"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send date options. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending date options: {str(e)}", db)
        return {"success": False, "error": str(e)}


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
        
        # Confirmation to user with center information
        await send_message_to_waid(wa_id, f"✅ Thank you! Your preferred appointment is {date_iso} at {time_label}{center_info}. Our team will call and confirm shortly.", db)
        # Clear state
        try:
            if wa_id in appointment_state:
                appointment_state.pop(wa_id, None)
        except Exception:
            pass
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
        body = await request.json()
        # Persist raw webhook payload to file for debugging/auditing
        try:
            log_dir = "webhook_logs"
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_path = os.path.join(log_dir, f"webhook_{ts}.json")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(json.dumps(body, ensure_ascii=False, indent=2))
        except Exception:
            pass
        # Handle different payload structures
        if "entry" in body:
            # Standard WhatsApp Business API webhook structure
            print(f"[ws_webhook] DEBUG - Using standard webhook structure")
            value = body["entry"][0]["changes"][0]["value"]
            contact = value["contacts"][0]
            message = value["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = value["metadata"]["display_phone_number"]
        else:
            # Alternative payload structure (direct structure)
            print(f"[ws_webhook] DEBUG - Using alternative payload structure")
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
        body_text = message[message_type].get("body", "")
        handled_text = False

        # Check prior messages first (before any early returns)
        prior_messages = message_service.get_messages_by_wa_id(db, wa_id)

        # Fetch or create customer
        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Check for referrer tracking in first message
        if len(prior_messages) == 0 and body_text:
            try:
                from services.referrer_service import referrer_service
                from schemas.referrer_schema import ReferrerTrackingCreate
                
                # Get referrer URL from request headers if available
                referrer_url = request.headers.get("referer", "")
                
                # Detect center information from message and referrer URL
                center_info = referrer_service.detect_center_from_message(body_text, referrer_url)
                
                # Try to extract UTM parameters from the message
                utm_data = referrer_service.parse_utm_parameters(body_text)
                
                # Create referrer tracking record
                referrer_data = ReferrerTrackingCreate(
                    wa_id=wa_id,
                    utm_source=utm_data.get('utm_source', ''),
                    utm_medium=utm_data.get('utm_medium', ''),
                    utm_campaign=utm_data.get('utm_campaign', ''),
                    utm_content=utm_data.get('utm_content', ''),
                    referrer_url=referrer_url,
                    center_name=center_info['center_name'],
                    location=center_info['location'],
                    customer_id=customer.id
                )
                referrer_service.create_referrer_tracking(db, referrer_data)
                
                # Log the detected center for debugging
                print(f"Detected center: {center_info['center_name']}, Location: {center_info['location']}")
                if referrer_url:
                    print(f"Referrer URL: {referrer_url}")
                    
            except Exception as e:
                print(f"Error tracking referrer: {e}")
                import traceback
                traceback.print_exc()

        # 1️⃣ Onboarding prompt (only for first message)
        # if len(prior_messages) == 0:
        #     await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)

        # 2️⃣ ADDRESS COLLECTION - Only through structured form (nudge once, not repeatedly)
        if awaiting_address_users.get(wa_id, False):
            raw_txt = (body_text or "") if message_type == "text" else ""
            norm_txt = re.sub(r"[^a-z]", "", raw_txt.lower())
            # While awaiting address, allow "buy/products/catalog" to pass through so catalog link is sent
            allow_catalog_shortcut = (
                message_type == "text" and (
                    ("buy" in norm_txt) or ("product" in norm_txt) or ("catalog" in norm_txt)
                )
            )
            # Skip welcome flow while awaiting address and do not spam nudges
            if message_type == "text" and norm_txt not in {"hi", "hello", "hlo"} and not allow_catalog_shortcut:
                if not address_nudge_sent.get(wa_id, False):
                    await send_message_to_waid(wa_id, "📍 Please use the address form above to enter your details. Click the '📝 Fill Address Form' button.", db)
                    address_nudge_sent[wa_id] = True
                return {"status": "awaiting_address_form", "message_id": message_id}

        # 3️⃣ AUTO WELCOME VALIDATION - Check for name and phone in text messages
        if message_type == "text":
            # First: persist inbound text and broadcast to websocket
            try:
                inbound_msg = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type="text",
                    body=body_text,
                    timestamp=timestamp,
                    customer_id=customer.id
                )
                message_service.create_message(db, inbound_msg)
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": "text",
                    "message": body_text,
                    "timestamp": timestamp.isoformat()
                })
            except Exception:
                pass
            # Normalize body text for consistent comparison
            def _normalize(txt: str) -> str:
                if not txt:
                    return ""
                try:
                    # replace fancy apostrophes/quotes with plain, remove non-letters/numbers/spaces
                    txt = txt.replace("'", "'").replace(""", '"').replace(""", '"')
                    txt = txt.lower().strip()
                    txt = re.sub(r"\s+", " ", txt)
                    return txt
                except Exception:
                    return txt.lower().strip()

            normalized_body = _normalize(body_text)
            
            # Prefill detection: if user sent the wa.link prefill message, send mr_welcome_temp
            allowed_variants = [
                _normalize("Hi, I’m interested in knowing more about your services. Please share details."),
                _normalize("Hi, I'm interested in knowing more about your services. Please share details."),
                _normalize("Hi I'm interested in knowing more about your services. Please share details."),
            ]
            if normalized_body in allowed_variants:
                print(f"[ws_webhook] DEBUG - Prefill detected, sending mr_welcome_temp")
                try:
                    token_entry_prefill = get_latest_token(db)
                    # Prefer phone_number_id from incoming webhook metadata if available
                    try:
                        incoming_phone_id = (value.get("metadata") or {}).get("phone_number_id")
                    except Exception:
                        incoming_phone_id = None
                    if token_entry_prefill and token_entry_prefill.token:
                        access_token_prefill = token_entry_prefill.token
                        phone_id_prefill = incoming_phone_id or os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                        lang_code_prefill = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                        body_components_prefill = [{
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": (sender_name or wa_id or "there")}
                            ]
                        }]
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template_attempt",
                                "message": "Sending mr_welcome_temp...",
                                "params": {"body_param_1": (sender_name or wa_id or "there"), "lang": lang_code_prefill, "phone_id": phone_id_prefill},
                                "timestamp": datetime.now().isoformat()
                            })
                        except Exception:
                            pass
                        from controllers.auto_welcome_controller import _send_template
                        resp_prefill = _send_template(
                            wa_id=wa_id,
                            template_name="mr_welcome_temp",
                            access_token=access_token_prefill,
                            phone_id=phone_id_prefill,
                            components=body_components_prefill,
                            lang_code=lang_code_prefill
                        )
                        print(f"[ws_webhook] DEBUG - mr_welcome_temp response status: {resp_prefill.status_code}")
                        try:
                            print(f"[ws_webhook] DEBUG - mr_welcome_temp response body: {str(resp_prefill.text)[:500]}")
                        except Exception:
                            pass
                        if resp_prefill.status_code == 200:
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template",
                                    "message": "mr_welcome_temp sent",
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception:
                                pass
                            handled_text = True
                            return {"status": "welcome_sent", "message_id": message_id}
                        else:
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template_error",
                                    "message": "mr_welcome_temp failed",
                                    "status_code": resp_prefill.status_code,
                                    "error": (resp_prefill.text[:500] if isinstance(resp_prefill.text, str) else str(resp_prefill.text)),
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception:
                                pass
                            handled_text = True
                            return {"status": "welcome_failed", "message_id": message_id}
                    else:
                        # No token available in this environment — broadcast for visibility
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template_error",
                                "message": "mr_welcome_temp not sent: no WhatsApp token",
                                "timestamp": datetime.now().isoformat()
                            })
                        except Exception:
                            pass
                        print(f"[ws_webhook] DEBUG - mr_welcome_temp not sent: no token available. incoming_phone_id={incoming_phone_id} env_phone_id={os.getenv('WHATSAPP_PHONE_ID')} lang={os.getenv('WELCOME_TEMPLATE_LANG')}")
                except Exception as e:
                    print(f"[ws_webhook] DEBUG - mr_welcome_temp send error: {e}")
                # Even if sending fails, continue to other logic below
            
            # Check for phone number patterns or name keywords
            has_phone = re.search(r"\b\d{10}\b", normalized_body) or re.search(r"\+91", normalized_body)
            has_name_keywords = any(keyword in normalized_body for keyword in ["name", "i am", "my name", "call me"])
            # Broader detection: two-word name + at least 7 digits anywhere triggers verification
            digit_count = len(re.findall(r"\d", normalized_body))
            has_two_word_name = bool(re.search(r"\b[A-Za-z]{2,}\s+[A-Za-z]{2,}\b", body_text))
            should_verify = bool(has_phone or has_name_keywords or (has_two_word_name and digit_count >= 7))
            
            print(f"[ws_webhook] DEBUG - message_type: {message_type}")
            print(f"[ws_webhook] DEBUG - normalized_body: '{normalized_body}'")
            print(f"[ws_webhook] DEBUG - has_phone: {has_phone}")
            print(f"[ws_webhook] DEBUG - has_name_keywords: {has_name_keywords}")
            print(f"[ws_webhook] DEBUG - digit_count: {digit_count}")
            print(f"[ws_webhook] DEBUG - has_two_word_name: {has_two_word_name}")
            print(f"[ws_webhook] DEBUG - should_verify: {should_verify}")
            
            if should_verify:
                print(f"[ws_webhook] DEBUG - Triggering contact verification")
                # Import the verification function from auto_welcome_controller
                from controllers.auto_welcome_controller import _verify_contact_with_openai
                verification = _verify_contact_with_openai(body_text)
                print(f"[ws_webhook] DEBUG - Verification result: {verification}")
                
                try:
                    print(f"[ws_webhook] DEBUG - Broadcasting contact_verification to websocket")
                    await manager.broadcast({
                        "from": to_wa_id,
                        "to": wa_id,
                        "type": "contact_verification",
                        "result": verification,
                        "timestamp": datetime.now().isoformat()
                    })
                    print(f"[ws_webhook] DEBUG - contact_verification broadcast successful")
                except Exception as e:
                    print(f"[ws_webhook] DEBUG - contact_verification broadcast failed: {e}")
                
                # Inform user on WhatsApp
                try:
                    if verification.get("valid"):
                        print(f"[ws_webhook] DEBUG - Verification valid, sending confirmation message")
                        await send_message_to_waid(wa_id, f"✅ Received details. Name: {verification.get('name')} | Phone: {verification.get('phone')}", db)
                        print(f"[ws_webhook] DEBUG - Confirmation message sent")
                        
                        # Send mr_treatment template (with name param) and fallback to interactive buttons on failure
                        try:
                            print(f"[ws_webhook] DEBUG - Attempting to send mr_treatment template")
                            token_entry_btn = get_latest_token(db)
                            if token_entry_btn and token_entry_btn.token:
                                print(f"[ws_webhook] DEBUG - Token found, proceeding with template")
                                access_token_btn = token_entry_btn.token
                                phone_id_btn = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                                lang_code_btn = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                # mr_treatment has 0 body placeholders; send without components
                                components_btn = None
                                
                                # Import the template sending function
                                from controllers.auto_welcome_controller import _send_template
                                resp_btn = _send_template(wa_id=wa_id, template_name="mr_treatment", access_token=token_entry_btn.token, phone_id=phone_id_btn, components=components_btn, lang_code=lang_code_btn)
                                print(f"[ws_webhook] DEBUG - Template response status: {resp_btn.status_code}")
                                try:
                                    print(f"[ws_webhook] DEBUG - Template response body: {str(resp_btn.text)[:500]}")
                                except Exception:
                                    pass
                                
                                if resp_btn.status_code == 200:
                                    print(f"[ws_webhook] DEBUG - Template sent successfully")
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "template",
                                            "message": "mr_treatment sent",
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    except Exception:
                                        pass
                                else:
                                    print(f"[ws_webhook] DEBUG - Template failed, sending fallback buttons")
                                    # Fallback to interactive buttons
                                    headers_btn = {"Authorization": f"Bearer {access_token_btn}", "Content-Type": "application/json"}
                                    payload_btn = {
                                        "messaging_product": "whatsapp",
                                        "to": wa_id,
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button",
                                            "body": {"text": "Please choose your area of concern:"},
                                            "action": {
                                                "buttons": [
                                                    {"type": "reply", "reply": {"id": "skin", "title": "Skin"}},
                                                    {"type": "reply", "reply": {"id": "hair", "title": "Hair"}},
                                                    {"type": "reply", "reply": {"id": "body", "title": "Body"}}
                                                ]
                                            }
                                        }
                                    }
                                    # Broadcast the error before fallback, so UI sees the reason
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "template_error",
                                            "message": "mr_treatment failed",
                                            "status_code": resp_btn.status_code,
                                            "error": (resp_btn.text[:500] if isinstance(resp_btn.text, str) else str(resp_btn.text)),
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    except Exception:
                                        pass
                                    requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "interactive",
                                            "message": "Please choose your area of concern:",
                                            "timestamp": datetime.now().isoformat(),
                                            "meta": {"kind": "buttons", "options": ["Skin", "Hair", "Body"]}
                                        })
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"[ws_webhook] DEBUG - Template sending failed: {e}")
                    else:
                        print(f"[ws_webhook] DEBUG - Verification not valid, composing corrective message")
                        issues = []
                        name_val = (verification.get('name') or '').strip() if isinstance(verification.get('name'), str) else None
                        phone_val = (verification.get('phone') or '').strip() if isinstance(verification.get('phone'), str) else None

                        # Name validation: at least 2 words, alphabetic
                        if not name_val:
                            issues.append("- Name missing")
                        else:
                            name_tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", name_val)
                            if len(name_tokens) < 2:
                                issues.append("- Name should have at least 2 words")

                        # Phone validation: +91XXXXXXXXXX or 10 digits
                        if not phone_val:
                            issues.append("- Phone number missing")
                        else:
                            digits = re.sub(r"\D", "", phone_val)
                            if digits.startswith("91") and len(digits) == 12:
                                digits = digits[2:]
                            if len(digits) != 10:
                                issues.append("- Phone must be 10 digits (Indian mobile)")

                        corrective = (
                            "❌ I couldn't verify your details.\n"
                            + ("\n".join(issues) + "\n" if issues else "")
                            + "\nPlease reply with your full name and a 10-digit mobile number in one message.\n"
                              "Example: Rahul Sharma 9876543210"
                        )
                        # Broadcast failure with details for UI/agents
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "contact_verification_failed",
                                "issues": issues,
                                "verification": verification,
                                "timestamp": datetime.now().isoformat()
                            })
                        except Exception:
                            pass
                        await send_message_to_waid(wa_id, corrective, db)
                        print(f"[ws_webhook] DEBUG - Corrective message sent")
                except Exception as e:
                    print(f"[ws_webhook] DEBUG - Error in validation flow: {e}")
                handled_text = True

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

        # 4️⃣ Regular text messages (non-address) - only if not already handled above
        if message_type == "text" and not handled_text:
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
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "text",
                "message": body_text,
                "timestamp": timestamp.isoformat()
            })

            # Catalog link is sent only on explicit button clicks; no text keyword trigger

        # 4️⃣ Hi/Hello auto-template (trigger only on whole-word greetings)
        raw = (body_text or "").strip()
        raw_lower = raw.lower()
        if message_type == "text" and re.search(r"\b(hi|hello|hlo)\b", raw_lower):
                # call your existing welcome template sending logic here
            token_entry = get_latest_token(db)
            if token_entry and token_entry.token:
                try:
                    access_token = token_entry.token
                    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                    # Resolve media_id: prefer env; else use last inbound image from this user; fallback to provided ID
                    media_id = os.getenv("WELCOME_TEMPLATE_MEDIA_ID") or "2185668755244609"
                    if not media_id:
                        try:
                            # Get prior messages for this user to find last image
                            user_prior_messages = message_service.get_messages_by_wa_id(db, wa_id)
                            last_images = [m for m in reversed(user_prior_messages) if m.type == "image" and m.media_id]
                            if last_images:
                                media_id = last_images[0].media_id
                        except Exception:
                            media_id = None

                    components = []
                    if media_id:
                        components.append({
                            "type": "header",
                            "parameters": [{"type": "image", "image": {"id": media_id}}]
                        })
                    components.append({
                        "type": "body",
                        "parameters": [{"type": "text", "text": sender_name}]
                    })

                    payload = {
                        "messaging_product": "whatsapp",
                        "to": wa_id,
                        "type": "template",
                        "template": {
                            "name": "welcome_msg",
                            "language": {"code": "en_US"},
                            **({"components": components} if components else {})
                        }
                    }

                    resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
                    if resp.status_code != 200:
                        print("Failed to send welcome template:", resp.text)
                    else:
                        try:
                            tpl_msg_id = resp.json()["messages"][0]["id"]
                            tpl_message = MessageCreate(
                                message_id=tpl_msg_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body=f"Welcome template sent to {sender_name}",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                                media_id=media_id if media_id else None
                            )
                            message_service.create_message(db, tpl_message)
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template",
                                "message": f"Welcome template sent to {sender_name}",
                                "timestamp": datetime.now().isoformat(),
                                **({"media_id": media_id} if media_id else {})
                            })
                        except Exception:
                            pass
                except Exception as _:
                    pass

        # Send onboarding prompt on very first message from this WA ID
        if len(prior_messages) == 0:
            await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)
        # (prompt already sent above on very first message)

        # (single hi/hello trigger handled above; removed duplicate block)

        # Auto-send welcome template if user said "hi"/"hello"/"hlo" and hasn't received one recently
        # if body_text.lower() in ["hi", "hello", "hlo"]:
        #     await send_welcome_template_to_waid(wa_id=from_wa_id, customer_name=sender_name, db=db)
        #     await manager.broadcast({
        #         "from": "system",
        #         "to": from_wa_id,
        #         "type": "template",
        #         "message": "Welcome template sent",
        #         "timestamp": datetime.now().isoformat()
        #     })
        #
        #
        # # result = await send_welcome_template_to_waid(wa_id=from_wa_id, customer_name=sender_name, db=db)
        # # return result

        if message_type == "order":
            order = message["order"]
            order_items = [
                OrderItemCreate(
                    product_retailer_id=prod["product_retailer_id"],
                    quantity=prod["quantity"],
                    item_price=prod["item_price"],
                    currency=prod["currency"]
                ) for prod in order["product_items"]
            ]
            order_data = OrderCreate(
                customer_id=customer.id,
                catalog_id=order["catalog_id"],
                timestamp=timestamp,
                items=order_items
            )
            order_obj = order_service.create_order(db, order_data)

            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "order",
                "catalog_id": order["catalog_id"],
                "products": order["product_items"],
                "timestamp": timestamp.isoformat(),
            })

            # NEW ADDRESS COLLECTION SYSTEM - Send "collect_address" template from Meta
            try:
                # Calculate order total
                total_amount = sum([p.get("item_price", 0) * p.get("quantity", 1) for p in order["product_items"]])
                
                # Get WhatsApp token
                token_entry = get_latest_token(db)
                if token_entry and token_entry.token:
                    access_token = token_entry.token
                    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                    
                    # Send collect_address template from Meta (no parameters)
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": wa_id,
                        "type": "template",
                        "template": {
                            "name": "collect_address",
                            "language": {"code": "en_US"}
                        }
                    }
                    
                    resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
                    if resp.status_code == 200:
                        try:
                            tpl_msg_id = resp.json()["messages"][0]["id"]
                            tpl_message = MessageCreate(
                                message_id=tpl_msg_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body=f"Address collection template sent to {customer.name or 'Customer'}",
                                timestamp=datetime.now(),
                                customer_id=customer.id
                            )
                            message_service.create_message(db, tpl_message)
                            
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template",
                                "message": f"Address collection template sent to {customer.name or 'Customer'}",
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            # Mark user as awaiting address for button responses and reset nudge flag
                            awaiting_address_users[wa_id] = True
                            address_nudge_sent[wa_id] = False
                            
                        except Exception as e:
                            print(f"Error saving collect_address template message: {e}")
                    else:
                        print(f"Failed to send collect_address template: {resp.text}")
                        # Fallback to structured form
                        await send_address_form(wa_id, db)
                else:
                    print("No WhatsApp token available for collect_address template")
                    # Fallback to structured form
                    await send_address_form(wa_id, db)
                    
            except Exception as e:
                print(f"Error sending collect_address template: {e}")
                # Fallback to structured form
                await send_address_form(wa_id, db)
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
            
            # Broadcast button click as a text message for frontend display
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "text",
                "message": f"🔘 {reply_text}",
                "timestamp": timestamp.isoformat(),
            })

            # Handle different button types
            choice_text = (reply_text or "").lower()

            # NEW: Support Skin/Hair/Body coming as type="button" (payload/text), not interactive.button_reply
            topic = (btn_id or btn_text or "").strip().lower()
            if topic in {"skin", "hair", "body"}:
                try:
                    token_entry2 = get_latest_token(db)
                    if token_entry2 and token_entry2.token:
                        access_token2 = token_entry2.token
                        phone_id2 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                        from controllers.auto_welcome_controller import _send_template
                        lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                        if topic == "skin":
                            # Send skin_treat_flow then the Skin concerns list (to mirror interactive path)
                            resp_skin = _send_template(wa_id=wa_id, template_name="skin_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template" if resp_skin.status_code == 200 else "template_error",
                                    "message": "skin_treat_flow sent" if resp_skin.status_code == 200 else "skin_treat_flow failed",
                                    **({"status_code": resp_skin.status_code} if resp_skin.status_code != 200 else {}),
                                })
                            except Exception:
                                pass

                            headers2 = {"Authorization": f"Bearer {access_token2}", "Content-Type": "application/json"}
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
                            requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                            return {"status": "list_sent", "message_id": message_id}

                        if topic == "hair":
                            resp_hair = _send_template(wa_id=wa_id, template_name="hair_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template" if resp_hair.status_code == 200 else "template_error",
                                    "message": "hair_treat_flow sent" if resp_hair.status_code == 200 else "hair_treat_flow failed",
                                    **({"status_code": resp_hair.status_code} if resp_hair.status_code != 200 else {}),
                                })
                            except Exception:
                                pass
                            return {"status": "hair_template_sent", "message_id": message_id}

                        if topic == "body":
                            resp_body = _send_template(wa_id=wa_id, template_name="body_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template" if resp_body.status_code == 200 else "template_error",
                                    "message": "body_treat_flow sent" if resp_body.status_code == 200 else "body_treat_flow failed",
                                    **({"status_code": resp_body.status_code} if resp_body.status_code != 200 else {}),
                                })
                            except Exception:
                                pass
                            return {"status": "body_template_sent", "message_id": message_id}
                except Exception:
                    pass

            # NEW: Support list selections arriving as type="button" (payload/text)
            norm_btn = (btn_id or btn_text or "").strip().lower()
            skin_concerns = {
                "acne / acne scars",
                "pigmentation",
                "uneven skin tone",
                "anti-aging ",
                "skin rejuvenation",
                "laser hair removal",
                "other skin concerns",
            }
            hair_concerns = {
                "hair loss / hair fall",
                "hair transplant",
                "dandruff & scalp care",
                "other hair concerns",
            }
            body_concerns = {
                "weight management",
                "body contouring",
                "weight loss",
                "other body concerns",
            }

            if norm_btn in skin_concerns or norm_btn in hair_concerns or norm_btn in body_concerns:
                # Mirror list_reply handling: send booking_appoint, then next-step buttons
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
                            })
                        except Exception:
                            pass
                except Exception:
                    pass

                # Send action buttons
                try:
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
                                "body": {"text": "Please choose one option:"},
                                "action": {
                                    "buttons": [
                                        {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 Book an Appointment"}},
                                        {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde Request a Call Back"}}
                                    ]
                                }
                            }
                        }
                        requests.post(get_messages_url(phone_id3), headers=headers3, json=payload_buttons)
                        return {"status": "next_actions_sent", "message_id": message_id}
                except Exception:
                    pass

            # 1) Buy Products: send catalog link ONLY for explicit Buy Products button
            if (btn_id and str(btn_id).lower() == "buy_products") or ((btn_text or "").strip().lower() == "buy products"):
                try:
                    await send_message_to_waid(wa_id, "🛍️ Browse our catalog: https://wa.me/c/917729992376", db)
                except Exception:
                    pass
                return {"status": "success", "message_id": message_id}

            # Appointment booking: trigger date list
            if ((btn_id or "").lower() == "book_appointment" or 
                (btn_text or "").strip().lower() == "book an appointment" or
                (btn.get("payload") or "").strip().lower() == "book an appointment"):
                try:
                    await send_date_list(wa_id, db)
                except Exception:
                    pass
                return {"status": "date_list_sent", "message_id": message_id}

            # Request a Call Back acknowledgement
            if ((btn_id or "").lower() == "request_callback" or 
                (btn_text or "").strip().lower() == "request a call back" or
                (btn.get("payload") or "").strip().lower() == "request a call back"):
                try:
                    await send_message_to_waid(wa_id, "📌 Thank you for your interest! One of our team members will contact you shortly to assist further.", db)
                except Exception:
                    pass
                return {"status": "callback_ack", "message_id": message_id}

            # Time selection via template button
            if ((btn_id or "").lower().startswith("time_") or 
                (btn_text or "").strip() in ["10:00 AM", "2:00 PM", "6:00 PM"] or
                (btn.get("payload") or "").strip() in ["10:00 AM", "2:00 PM", "6:00 PM"]):
                try:
                    time_map = {
                        "time_10_00": "10:00 AM",
                        "time_14_00": "2:00 PM",
                        "time_18_00": "6:00 PM",
                    }
                    time_label = (time_map.get((btn_id or "").lower()) or 
                                (btn_text or "").strip() or 
                                (btn.get("payload") or "").strip())
                    date_iso = (appointment_state.get(wa_id) or {}).get("date")
                    if date_iso and time_label:
                        await _confirm_appointment(wa_id, db, date_iso, time_label)
                        return {"status": "appointment_captured", "message_id": message_id}
                    else:
                        await send_message_to_waid(wa_id, "Please select a date first.", db)
                        await send_date_list(wa_id, db)
                        return {"status": "need_date_first", "message_id": message_id}
                except Exception:
                    pass

            # 2) Address collection buttons (including collect_address template buttons and flow buttons)
            if btn_id in ["ADD_DELIVERY_ADDRESS", "USE_CURRENT_LOCATION", "ENTER_NEW_ADDRESS", 
                         "USE_SAVED_ADDRESS", "CONFIRM_ADDRESS", "CHANGE_ADDRESS", "RETRY_ADDRESS",
                         "add_address", "use_location", "enter_manually", "saved_address",
                         "fill_form_step1", "share_location", "provide_address", "address_flow"]:
                try:
                    # Handle WhatsApp Flow buttons
                    if btn_id in ["provide_address", "address_flow"]:
                        # Flow button clicked - send the WhatsApp Flow
                        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                        await send_address_flow_button(wa_id, db, customer.name or "Customer")
                    
                    # Handle collect_address template buttons - any button from collect_address template opens the form
                    elif btn_id in ["add_address", "use_location", "enter_manually", "saved_address", "fill_form_step1", "share_location"]:
                        if btn_id == "add_address" or btn_id == "enter_manually" or btn_id == "fill_form_step1":
                            # Show structured address form using WhatsApp interactive message
                            await send_address_form(wa_id, db)
                        elif btn_id == "use_location" or btn_id == "share_location":
                            await send_message_to_waid(wa_id, "📍 Please share your current location by tapping the location icon below.", db)
                        elif btn_id == "saved_address":
                            await send_message_to_waid(wa_id, "💾 You can use a previously saved address. Please enter your address manually for now.", db)
                            await send_address_form(wa_id, db)
                    else:
                        # Handle other address collection buttons using the service
                        from services.address_collection_service import AddressCollectionService
                        address_service = AddressCollectionService(db)
                        result = await address_service.handle_address_button_click(wa_id, btn_id)
                        
                        if not result["success"]:
                            await send_message_to_waid(wa_id, f"❌ {result.get('error', 'Something went wrong')}", db)
                except Exception as e:
                    await send_message_to_waid(wa_id, f"❌ Error processing address request: {str(e)}", db)
            
            # 3) Generic handler for any button click when user is awaiting address (not for buy)
            elif awaiting_address_users.get(wa_id, False):
                # If user is awaiting address and clicks any button, show the structured form
                await send_address_form(wa_id, db)

            return {"status": "success", "message_id": message_id}

        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            i_type = interactive.get("type")
            title = None
            reply_id = None
            
            # Handle WhatsApp Flow submission
            if i_type == "flow":
                flow_response = interactive.get("flow_response", {})
                flow_token = flow_response.get("flow_token", "")
                flow_id = flow_response.get("flow_id", "")
                flow_cta = flow_response.get("flow_cta", "")
                flow_action_payload = flow_response.get("flow_action_payload", {})
                
                print(f"Flow response received: flow_id={flow_id}, flow_cta={flow_cta}")

                # Broadcast raw flow response to frontend for visibility/debug
                try:
                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": to_wa_id,
                        "type": "flow_response",
                        "flow_id": flow_id,
                        "flow_cta": flow_cta,
                        "payload": flow_action_payload,
                        "timestamp": timestamp.isoformat(),
                    })
                except Exception:
                    pass
                
                # Handle address collection flow
                if flow_id == "address_collection_flow" or "address" in flow_id.lower():
                    try:
                        # Extract address data from flow response
                        address_data = {}
                        
                        # Parse flow action payload for address fields
                        if flow_action_payload:
                            # Common field mappings for address flows
                            field_mappings = {
                                "full_name": ["full_name", "name", "customer_name"],
                                "phone_number": ["phone_number", "phone", "mobile"],
                                "house_street": ["house_street", "address_line_1", "street"],
                                "locality": ["locality", "area", "neighborhood"],
                                "city": ["city", "town"],
                                "state": ["state", "province"],
                                "pincode": ["pincode", "postal_code", "zip_code"],
                                "landmark": ["landmark", "landmark_nearby"]
                            }
                            
                            for field_name, possible_keys in field_mappings.items():
                                for key in possible_keys:
                                    if key in flow_action_payload:
                                        address_data[field_name] = flow_action_payload[key]
                                        break
                        
                        # Validate and save address
                        if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                            from schemas.address_schema import CustomerAddressCreate
                            from services.address_service import create_customer_address
                            
                            address_create = CustomerAddressCreate(
                                customer_id=customer.id,
                                full_name=address_data.get("full_name", ""),
                                house_street=address_data.get("house_street", ""),
                                locality=address_data.get("locality", ""),
                                city=address_data.get("city", ""),
                                state=address_data.get("state", ""),
                                pincode=address_data.get("pincode", ""),
                                landmark=address_data.get("landmark", ""),
                                phone=address_data.get("phone_number", customer.wa_id),
                                address_type="home",
                                is_default=True
                            )
                            
                            saved_address = create_customer_address(db, address_create)
                            
                            # Send confirmation
                            await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                            await send_message_to_waid(wa_id, f"📍 {saved_address.full_name}, {saved_address.house_street}, {saved_address.locality}, {saved_address.city} - {saved_address.pincode}", db)
                            
                            # Clear awaiting address flag
                            awaiting_address_users[wa_id] = False
                            
                            # Continue with payment flow
                            try:
                                latest_order = (
                                    db.query(order_service.Order)
                                    .filter(order_service.Order.customer_id == customer.id)
                                    .order_by(order_service.Order.timestamp.desc())
                                    .first()
                                )
                                total_amount = 0
                                if latest_order:
                                    for item in latest_order.items:
                                        qty = item.quantity or 1
                                        price = item.item_price or item.price or 0
                                        total_amount += float(price) * int(qty)
                                
                                if total_amount > 0:
                                    # Send payment link (using existing payment logic)
                                    from utils.razorpay_utils import create_razorpay_payment_link
                                    try:
                                        payment_resp = create_razorpay_payment_link(
                                            amount=float(total_amount),
                                            currency="INR",
                                            description=f"WA Order {str(latest_order.id) if latest_order else ''}"
                                        )
                                        pay_link = payment_resp.get("short_url") if isinstance(payment_resp, dict) else None
                                        if pay_link:
                                            await send_message_to_waid(wa_id, f"💳 Please complete your payment using this link: {pay_link}", db)
                                    except Exception as pay_err:
                                        print("Payment flow error:", pay_err)
                            except Exception as e:
                                print("Error in payment flow after address collection:", e)
                            
                            return {"status": "address_saved", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).", db)
                            return {"status": "flow_incomplete", "message_id": message_id}
                            
                    except Exception as e:
                        print(f"Error processing flow response: {e}")
                        await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                        return {"status": "flow_error", "message_id": message_id}
                
                return {"status": "flow_processed", "message_id": message_id}
            
            # Handle form submission
            elif i_type == "form":
                form_response = interactive.get("form_response", {})
                form_name = form_response.get("name", "")
                form_data = form_response.get("data", [])
                
                if form_name == "address_form":
                    # Process address form submission
                    try:
                        address_data = {}
                        for item in form_data:
                            field_id = item.get("id", "")
                            field_value = item.get("value", "")
                            address_data[field_id] = field_value
                        
                        # Validate and save address
                        if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                            # Create address using the new address service
                            from schemas.address_schema import CustomerAddressCreate
                            from services.address_service import create_customer_address
                            
                            address_create = CustomerAddressCreate(
                                customer_id=customer.id,
                                full_name=address_data.get("full_name", ""),
                                house_street=address_data.get("house_street", ""),
                                locality=address_data.get("locality", ""),
                                city=address_data.get("city", ""),
                                state=address_data.get("state", ""),
                                pincode=address_data.get("pincode", ""),
                                landmark=address_data.get("landmark", ""),
                                phone=address_data.get("phone_number", customer.wa_id),
                                address_type="home",
                                is_default=True
                            )
                            
                            saved_address = create_customer_address(db, address_create)
                            
                            # Send confirmation
                            await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                            await send_message_to_waid(wa_id, f"📍 {saved_address.full_name}, {saved_address.house_street}, {saved_address.locality}, {saved_address.city} - {saved_address.pincode}", db)
                            
                            # Clear awaiting address flag
                            awaiting_address_users[wa_id] = False
                            
                            # Continue with payment flow
                            try:
                                latest_order = (
                                    db.query(order_service.Order)
                                    .filter(order_service.Order.customer_id == customer.id)
                                    .order_by(order_service.Order.timestamp.desc())
                                    .first()
                                )
                                total_amount = 0
                                if latest_order:
                                    for item in latest_order.items:
                                        qty = item.quantity or 1
                                        price = item.item_price or item.price or 0
                                        total_amount += float(price) * int(qty)

                                if total_amount > 0:
                                    # Send payment link (using existing payment logic)
                                    await send_message_to_waid(wa_id, f"💳 Please complete your payment of ₹{int(total_amount)} using the payment link that will be sent shortly.", db)
                            except Exception as pay_err:
                                print("Payment flow error:", pay_err)
                            
                            return {"status": "address_saved", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).", db)
                            return {"status": "form_incomplete", "message_id": message_id}
                            
                    except Exception as e:
                        print(f"Error processing address form: {e}")
                        await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                        return {"status": "form_error", "message_id": message_id}
            
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
                            # Send to WA API (no websocket broadcast of list to avoid duplicates)
                            requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
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

                      
                        # Send to WhatsApp API (no extra websocket broadcast here to avoid duplicates)
                        requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                        return {"status": "list_sent", "message_id": message_id}
            except Exception:
                pass

            # Appointment booking entry shortcuts
            try:
                if i_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = button_reply.get("id", "")
                    button_title = button_reply.get("title", "")
                    
                    if ((button_id or "").lower() == "book_appointment" or 
                        (button_title or "").strip().lower() == "book an appointment"):
                        await send_date_list(wa_id, db)
                        return {"status": "date_list_sent", "message_id": message_id}
                    
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
                        else:
                            await send_message_to_waid(wa_id, "Please select a date first.", db)
                            await send_date_list(wa_id, db)
                            return {"status": "need_date_first", "message_id": message_id}
            except Exception:
                pass

            # Step 3 → 6: After a list selection, save+broadcast reply, then present next-step action buttons
            try:
                if i_type == "list_reply" and (reply_id or title):
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
                                "body": {"text": "Please choose one option:"},
                                "action": {
                                    "buttons": [
                                        {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 Book an Appointment"}},
                                        {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde Request a Call Back"}}
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
                                "message": "Please choose one option:",
                                "timestamp": timestamp.isoformat(),
                                "meta": {"kind": "buttons", "options": ["Book an Appointment", "Request a Call Back"]}
                            })
                        except Exception:
                            pass
                        # Then attempt to send to WhatsApp API
                        requests.post(get_messages_url(phone_id3), headers=headers3, json=payload_buttons)
                        return {"status": "next_actions_sent", "message_id": message_id}
            except Exception:
                pass

            # Save user's interactive reply (fallback if not already broadcasted above)
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
            message_service.create_message(db, msg_interactive)
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "interactive",
                "message": reply_text,
                "timestamp": timestamp.isoformat(),
            })

            # If user chose Buy Products → send only the WhatsApp catalog link (strict match)
            try:
                reply_text  # may be undefined if we already broadcast earlier
            except NameError:
                reply_text = title or reply_id or ""
            choice_text = (reply_text or "").strip().lower()
            if (reply_id and reply_id.lower() == "buy_products") or (choice_text == "buy products"):
                try:
                    await send_message_to_waid(wa_id, "🛍️ Browse our catalog: https://wa.me/c/917729992376", db)
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
        
        elif message_type != "text":
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
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": message_type,
                "message": message_data.body,
                "timestamp": message_data.timestamp.isoformat()
            })

        return {"status": "success", "message_id": message_id}

    except Exception as e:
        print("Webhook error:", e)
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