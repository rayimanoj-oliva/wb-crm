"""
City Selection for Lead-to-Appointment Booking Flow
Handles city selection with quick replies
"""

from datetime import datetime
from typing import Dict, Any
import requests

from sqlalchemy.orm import Session
from services.whatsapp_service import get_latest_token
from .config import LEAD_APPOINTMENT_PHONE_ID, LEAD_APPOINTMENT_DISPLAY_LAST10
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def send_city_selection(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send city selection with quick replies.
    
    Returns a status dict.
    """
    # Global guard: avoid duplicate city and concern prompts within a short window
    try:
        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
        _st = _appt_state.get(wa_id) or {}
        from datetime import datetime as _dt
        last_sent = _st.get("city_prompt_ts")
        if isinstance(last_sent, str):
            try:
                if (_dt.now() - _dt.fromisoformat(last_sent)).total_seconds() < 8:
                    return {"status": "city_prompt_recently_sent"}
            except Exception:
                pass
        _st["city_prompt_ts"] = _dt.now().isoformat()
        _appt_state[wa_id] = _st
    except Exception:
        pass

    try:
        # Resolve credentials for dedicated lead appointment number
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send city options right now.", db)
            return {"success": False, "error": "no_token"}
        access_token = token_entry.token
        phone_id = str(LEAD_APPOINTMENT_PHONE_ID)
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

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
                # "header": {"type": "text", "text": "City Selection"},
                "body": {"text": "Please select your city:"},
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
            message_id = f"outbound_{datetime.now().timestamp()}"
            try:
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", message_id)
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate
                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=("91" + LEAD_APPOINTMENT_DISPLAY_LAST10),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Please select your city:",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                # Choose display "from" matching the phone_id we used to send
                try:
                    display_from = "91" + LEAD_APPOINTMENT_DISPLAY_LAST10
                except Exception:
                    display_from = "91" + LEAD_APPOINTMENT_DISPLAY_LAST10
                await manager.broadcast({
                    "from": display_from,
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Please select your city:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Cities"}
                })
                
                # Log last step reached: city_selection
                try:
                    from utils.flow_log import log_last_step_reached
                    from services.customer_service import get_customer_record_by_wa_id
                    _cust = get_customer_record_by_wa_id(db, wa_id)
                    log_last_step_reached(
                        db,
                        flow_type="lead_appointment",
                        step="city_selection",
                        wa_id=wa_id,
                        name=(getattr(_cust, "name", None) or "") if _cust else None,
                    )
                    print(f"[lead_appointment_flow] ✅ Logged last step: city_selection")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not log last step: {e}")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            # Arm Follow-Up 1 after this outbound prompt in case user stops here
            try:
                import asyncio
                from .follow_up1 import schedule_follow_up1_after_welcome
                asyncio.create_task(schedule_follow_up1_after_welcome(wa_id, datetime.utcnow()))
            except Exception:
                pass
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
        
        # Always use dedicated lead appointment phone id
        phone_id = str(LEAD_APPOINTMENT_PHONE_ID)

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
                "body": {"text": "Please select your city:"},
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
    customer: Any,
    phone_number_id: str | None = None,
    to_wa_id: str | None = None
) -> Dict[str, Any]:
    """Handle city selection response.
    
    Args:
        reply_id: City ID like "city_hyderabad", "city_bengaluru", etc.
        phone_number_id: The phone_number_id from webhook metadata (to verify this is lead appointment flow)
        to_wa_id: The display phone number (to verify this is lead appointment flow)
        
    Returns a status dict.
    """
    
    # CRITICAL: Only handle city selection if this is actually a lead appointment flow number
    # This prevents overlap with treatment flow city selection
    is_lead_appointment_number = False
    try:
        from .config import LEAD_APPOINTMENT_PHONE_ID
        if phone_number_id and str(phone_number_id) == str(LEAD_APPOINTMENT_PHONE_ID):
            is_lead_appointment_number = True
        elif to_wa_id:
            # Fallback: check by display phone number
            import re as _re
            from .config import LEAD_APPOINTMENT_DISPLAY_LAST10
            disp_digits = _re.sub(r"\D", "", to_wa_id or "")
            disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
            if disp_last10 == LEAD_APPOINTMENT_DISPLAY_LAST10:
                is_lead_appointment_number = True
        # Also check flow context from state
        if not is_lead_appointment_number:
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                st_ctx = appointment_state.get(wa_id) or {}
                flow_ctx = st_ctx.get("flow_context")
                # If explicitly in treatment flow, skip
                if flow_ctx == "treatment":
                    print(f"[lead_appointment_flow] DEBUG - Skipping city selection: in treatment flow context")
                    return {"status": "skipped", "reason": "treatment_flow_context"}
                # If explicitly in lead appointment flow, allow
                if flow_ctx == "lead_appointment":
                    is_lead_appointment_number = True
            except Exception:
                pass
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not verify lead appointment number: {e}")
    
    if not is_lead_appointment_number:
        print(f"[lead_appointment_flow] DEBUG - Skipping city selection: not a lead appointment number (phone_id={phone_number_id}, to_wa_id={to_wa_id})")
        return {"status": "skipped", "reason": "not_lead_appointment_number"}
    
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
        phone_id_hint = LEAD_APPOINTMENT_PHONE_ID
        await send_message_to_waid(wa_id, "❌ Invalid city selection. Please try again.", db, phone_id_hint=str(phone_id_hint))
        return {"status": "invalid_selection"}
    
    # Store selected city in customer data or session and establish idempotency keys
    try:
        from controllers.web_socket import lead_appointment_state, appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        # Soft idempotency: only skip if same reply_id AND clinic location was sent recently (within last 60s)
        last_city_reply = lead_appointment_state[wa_id].get("last_city_reply_id")
        clinic_sent = lead_appointment_state[wa_id].get("clinic_location_sent")
        if last_city_reply == (reply_id or "").strip().lower() and clinic_sent:
            # Check timestamp - only block if sent very recently
            clinic_ts = lead_appointment_state[wa_id].get("clinic_location_sent_ts")
            if clinic_ts:
                try:
                    from datetime import datetime as _dt_check
                    ts_obj = _dt_check.fromisoformat(clinic_ts) if isinstance(clinic_ts, str) else None
                    if ts_obj and (_dt_check.now() - ts_obj).total_seconds() < 60:
                        return {"status": "city_already_handled", "city": selected_city}
                except Exception:
                    pass

        lead_appointment_state[wa_id]["last_city_reply_id"] = (reply_id or "").strip().lower()
        lead_appointment_state[wa_id]["selected_city"] = selected_city
        print(f"[lead_appointment_flow] DEBUG - Stored city selection: {selected_city}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not store city selection: {e}")
    
    # Lead appointment flow only: proceed to clinic selection with dedicated number
    phone_id_hint = LEAD_APPOINTMENT_PHONE_ID
    await send_message_to_waid(wa_id, f"✅ Great! You selected {selected_city}.", db, phone_id_hint=str(phone_id_hint))
    
    from .clinic_location import send_clinic_location
    # Use selected city directly (no normalization needed)
    result = await send_clinic_location(db, wa_id=wa_id, city=selected_city)
    return {"status": "proceed_to_clinic_location", "city": selected_city, "result": result}
