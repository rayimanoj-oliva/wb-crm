"""
City Selection for Lead-to-Appointment Booking Flow
Handles city selection with quick replies
"""

from datetime import datetime
from typing import Dict, Any
import os
import requests

from sqlalchemy.orm import Session
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def send_city_selection(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send city selection with quick replies.
    
    Returns a status dict.
    """
    
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send city options right now.", db)
            return {"success": False, "error": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        # Page 1 (exactly 10 rows as requested)
        rows_page1 = [
            {"id": "city_hyderabad", "title": "Hyderabad"},
            {"id": "city_bangalore", "title": "Bangalore"},
            {"id": "city_chennai", "title": "Chennai"},
            {"id": "city_kolkata", "title": "Kolkata"},
            {"id": "city_pune", "title": "Pune"},
            {"id": "city_kochi", "title": "Kochi"},
            {"id": "city_ahmedabad", "title": "Ahmedabad"},
            {"id": "city_ludhiana", "title": "Ludhiana"},
            {"id": "city_vizag", "title": "Vizag"},
            {"id": "city_vijayawada", "title": "Vijayawada"},
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "City Selection"},
                "body": {"text": "Please select your city from the list below 👇"},
                "action": {
                    "button": "Choose City",
                    "sections": [
                        {"title": "Available Cities", "rows": rows_page1}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        if resp.status_code == 200:
            try:
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate
                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Please select your city from the list below 👇",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Please select your city from the list below 👇",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Cities"}
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            return {"success": True, "message_id": message_id}
        else:
            try:
                print(f"[lead_appointment_flow] ERROR - City list send failed: status={resp.status_code} body={resp.text}")
            except Exception:
                pass
            # Fallback already handled by caller if needed
            await send_message_to_waid(wa_id, "❌ Could not send city options. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending city options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def send_city_selection_page2(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send the remaining cities (second page) as an interactive list."""
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send more cities right now.", db)
            return {"success": False, "error": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows_page2 = [
            {"id": "city_vizag", "title": "Vizag"},
            {"id": "city_vijayawada", "title": "Vijayawada"},
            {"id": "city_other", "title": "Other"},
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "More Cities"},
                "body": {"text": "Please select your city from the list below 👇"},
                "action": {
                    "button": "Choose City",
                    "sections": [
                        {"title": "More Cities", "rows": rows_page2}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            return {"success": True}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send more city options. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending more city options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_city_selection(
    db: Session, 
    *, 
    wa_id: str, 
    reply_id: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle city selection response.
    
    Args:
        reply_id: City ID like "city_hyderabad", "city_bengaluru", etc.
        
    Returns a status dict.
    """
    
    # Paging support
    if (reply_id or "").strip().lower() == "city_more":
        return await send_city_selection_page2(db, wa_id=wa_id)

    # Map city IDs to city names
    city_mapping = {
        "city_hyderabad": "Hyderabad",
        "city_bangalore": "Bangalore",
        "city_chennai": "Chennai",
        "city_kolkata": "Kolkata",
        "city_pune": "Pune",
        "city_kochi": "Kochi",
        "city_ahmedabad": "Ahmedabad",
        "city_ludhiana": "Ludhiana",
        "city_vizag": "Vizag",
        "city_vijayawada": "Vijayawada",
    }
    
    normalized_reply = (reply_id or "").strip().lower()
    selected_city = city_mapping.get(normalized_reply)
    
    if not selected_city:
        await send_message_to_waid(wa_id, "❌ Invalid city selection. Please try again.", db)
        return {"status": "invalid_selection"}
    
    # Store selected city in customer data or session
    try:
        from controllers.web_socket import lead_appointment_state, appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        lead_appointment_state[wa_id]["selected_city"] = selected_city
        print(f"[lead_appointment_flow] DEBUG - Stored city selection: {selected_city}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not store city selection: {e}")
    
    # Determine flow context
    context = None
    try:
        from controllers.web_socket import appointment_state as _appt_state
        context = ((_appt_state.get(wa_id) or {}).get("flow_context"))
    except Exception:
        context = None
    if not context:
        try:
            from controllers.web_socket import lead_appointment_state as _lead_state
            context = ((_lead_state.get(wa_id) or {}).get("flow_context"))
        except Exception:
            context = None

    # Treatment flow: ask for name/number confirmation directly
    if context == "treatment":
        await send_message_to_waid(wa_id, f"✅ Great! You selected {selected_city}.", db)
        # Flag treatment flow confirmation path
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            st["from_treatment_flow"] = True
            appointment_state[wa_id] = st
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not set from_treatment_flow flag: {e}")

        # Ask for name/number confirmation (reuse existing pattern)
        try:
            from services.customer_service import get_customer_record_by_wa_id
            customer_rec = get_customer_record_by_wa_id(db, wa_id)
            display_name = (customer_rec.name.strip() if customer_rec and isinstance(customer_rec.name, str) else None) or "there"
            try:
                import re as _re
                digits = _re.sub(r"\D", "", wa_id)
                last10 = digits[-10:] if len(digits) >= 10 else None
                display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
            except Exception:
                display_phone = wa_id
            confirm_msg = (
                f"Please confirm your name and contact number:\n*{display_name}*\n*{display_phone}*"
            )
            await send_message_to_waid(wa_id, confirm_msg, db)

            # Send Yes/No confirmation buttons
            token_entry = get_latest_token(db)
            if token_entry and token_entry.token:
                access_token = token_entry.token
                phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                payload_btn = {
                    "messaging_product": "whatsapp",
                    "to": wa_id,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": "Is this name and number correct?"},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes"}},
                                {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}},
                            ]
                        },
                    },
                }
                import requests as _req
                from config.constants import get_messages_url as _gm
                _req.post(_gm(phone_id), headers=headers, json=payload_btn)
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not send confirmation prompt: {e}")

        return {"status": "awaiting_confirmation", "city": selected_city}

    # Lead appointment flow: proceed to clinic selection
    else:
        from .clinic_location import send_clinic_location
        # Normalize city for clinic mapping (e.g., Bangalore -> Bengaluru)
        city_for_clinic = selected_city
        if selected_city == "Bangalore":
            city_for_clinic = "Bengaluru"
        result = await send_clinic_location(db, wa_id=wa_id, city=city_for_clinic)
        return {"status": "proceed_to_clinic_location", "city": selected_city, "result": result}
