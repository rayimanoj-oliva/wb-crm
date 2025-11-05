import os
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from sqlalchemy.orm import Session

from config.constants import get_messages_url
from services.whatsapp_service import get_latest_token
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager
from controllers.state.memory import appointment_state  # keep state centralized


async def send_time_buttons(wa_id: str, db: Session) -> Dict[str, Any]:
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


async def confirm_appointment(wa_id: str, db: Session, date_iso: str, time_label: str) -> Dict[str, Any]:
    """
    Public wrapper around the internal confirmation logic.
    Kept separate so controllers can import a single public function.
    """
    return await _confirm_appointment(wa_id, db, date_iso, time_label)


async def _confirm_appointment(wa_id: str, db: Session, date_iso: str, time_label: str) -> Dict[str, Any]:
    try:
        # Get referrer info (optional)
        center_info = ""
        try:
            from services.referrer_service import referrer_service
            referrer = referrer_service.get_referrer_by_wa_id(db, wa_id)
            if referrer and referrer.center_name:
                center_info = f" at {referrer.center_name}, {referrer.location}"
        except Exception:
            pass

        # Prepare confirmation prompt with pre-filled name/phone
        try:
            from services.customer_service import get_customer_record_by_wa_id
            customer = get_customer_record_by_wa_id(db, wa_id)
            display_name = (customer.name.strip() if customer and isinstance(customer.name, str) else None) or "there"
        except Exception:
            display_name = "there"

        # Derive phone from wa_id as +91XXXXXXXXXX when possible
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

        # Follow-up interactive Yes/No
        try:
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
                try:
                    _resp_btn = requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                    try:
                        print(f"[ws_webhook] DEBUG - confirm buttons sent phone_id={phone_id_btn} status={_resp_btn.status_code}")
                    except Exception:
                        pass
                except Exception as _e_btn:
                    print(f"[ws_webhook] ERROR - confirm buttons post failed: {_e_btn}")
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

        # Heads-up broadcast
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
