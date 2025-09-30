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
from controllers.components.welcome_flow import run_welcome_flow, trigger_buy_products_from_welcome
from controllers.components.treament_flow import run_treament_flow, run_treatment_buttons_flow
from controllers.components.interactive_type import run_interactive_type
from controllers.components.products_flow import run_buy_products_flow

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

async def _send_address_text_guidance(wa_id: str, db: Session):
    try:
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
    except Exception:
        pass


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
        await send_message_to_waid(wa_id, f"✅ Thank you! Your preferred appointment is {date_iso} at {time_label}. Our team will call and confirm shortly.", db)
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

        # 3️⃣ AUTO WELCOME VALIDATION - extracted to component function
        handled_text = False
        if message_type == "text":
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
        if len(prior_messages) == 0:
            await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)
      


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
                        # Fallback to simple text guidance
                        await _send_address_text_guidance(wa_id, db)
                else:
                    print("No WhatsApp token available for collect_address template")
                    # Fallback to simple text guidance
                    await _send_address_text_guidance(wa_id, db)
                    
            except Exception as e:
                print(f"Error sending collect_address template: {e}")
                # Fallback to simple text guidance
                await _send_address_text_guidance(wa_id, db)
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
                return {"status": "success", "message_id": message_id}

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

            # 2) Address collection buttons (including collect_address template buttons and flow buttons)
            if btn_id in ["ADD_DELIVERY_ADDRESS", "USE_CURRENT_LOCATION", "ENTER_NEW_ADDRESS", 
                         "USE_SAVED_ADDRESS", "CONFIRM_ADDRESS", "CHANGE_ADDRESS", "RETRY_ADDRESS",
                         "add_address", "use_location", "enter_manually", "saved_address",
                         "fill_form_step1", "share_location", "provide_address", "address_flow"]:
                try:
                    # Handle WhatsApp Flow buttons
                    if btn_id in ["provide_address", "address_flow"]:
                        # Flow button clicked - fallback to simple text guidance
                        await _send_address_text_guidance(wa_id, db)
                    
                    # Handle collect_address template buttons - any button from collect_address template opens the form
                    elif btn_id in ["add_address", "use_location", "enter_manually", "saved_address", "fill_form_step1", "share_location"]:
                        if btn_id == "add_address" or btn_id == "enter_manually" or btn_id == "fill_form_step1":
                            # Fallback to simple text guidance
                            await _send_address_text_guidance(wa_id, db)
                        elif btn_id == "use_location" or btn_id == "share_location":
                            await send_message_to_waid(wa_id, "📍 Please share your current location by tapping the location icon below.", db)
                        elif btn_id == "saved_address":
                            await send_message_to_waid(wa_id, "💾 You can use a previously saved address. Please enter your address manually for now.", db)
                            await _send_address_text_guidance(wa_id, db)
                    else:
                        # Handle other address collection buttons using the service
                        # AddressCollectionService removed; fallback to simple text guidance
                        await _send_address_text_guidance(wa_id, db)
                except Exception as e:
                    await send_message_to_waid(wa_id, f"❌ Error processing address request: {str(e)}", db)
            
            # 3) Generic handler for any button click when user is awaiting address (not for buy)
            elif awaiting_address_users.get(wa_id, False):
                # If user is awaiting address and clicks any button, show guidance
                await _send_address_text_guidance(wa_id, db)

            return {"status": "success", "message_id": message_id}

        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            i_type = interactive.get("type")
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