import os
import requests
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from config.constants import get_messages_url
from models.models import Message
from schemas.message_schema import MessageCreate
from services import message_service
from services.whatsapp_service import get_latest_token
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager
from controllers.state.memory import awaiting_address_users, address_nudge_sent, generate_flow_token

# Expose a single entry point that callers can use.
async def send_address_flow_directly(wa_id: str, db: Session, customer_id: Optional[int] = None):
    try:
        if customer_id:
            from services.address_service import get_customer_addresses
            saved_addresses = get_customer_addresses(db, customer_id)
            if saved_addresses:
                await _send_smart_address_selection(wa_id, db, saved_addresses, customer_id)
                return
        await _send_address_form_directly(wa_id, db, customer_id)
    except Exception as e:
        print(f"Error in send_address_flow_directly: {e}")
        await send_message_to_waid(wa_id, "❌ Unable to send address form right now. Please try again later.", db)

async def _send_smart_address_selection(wa_id: str, db: Session, saved_addresses: list, customer_id: Optional[int]):
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address selection right now. Please try again later.", db)
            return

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = []
        for addr in saved_addresses[:10]:
            title = f"{addr.full_name[:35]}"
            subtitle = f"{addr.house_street[:60]} | {addr.city} - {addr.pincode}"
            rows.append({
                "id": f"use_address_{addr.id}",
                "title": title,
                "description": subtitle,
            })

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
                    "sections": [{
                        "title": "Saved Addresses",
                        "rows": rows
                    }]
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
                db.commit()

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
            await _send_address_form_directly(wa_id, db, customer_id)
    except Exception as e:
        print(f"Error in _send_smart_address_selection: {e}")
        await _send_address_form_directly(wa_id, db, customer_id)

async def _send_address_form_directly(wa_id: str, db: Session, customer_id: Optional[int]):
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address form right now. Please try again later.", db)
            return

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

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
                db.commit()

                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address collection flow sent",
                    "timestamp": datetime.now().isoformat()
                })

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
