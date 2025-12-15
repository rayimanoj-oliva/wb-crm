"""
Auto Welcome Message for Lead-to-Appointment Booking Flow
Sends the initial welcome template message (oliva_meta_ad)
"""

from datetime import datetime
from typing import Dict, Any, Optional
import os
import re
import requests

from sqlalchemy.orm import Session
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager
from marketing.whatsapp_numbers import WHATSAPP_NUMBERS, get_number_config


def _resolve_lead_phone_id(wa_id: str) -> tuple[Optional[str], Optional[str], str]:
    """Resolve phone_id and token for lead appointment flow.

    Returns (token, phone_id, display_number).
    Priority:
    1) Stored incoming_phone_id (the number customer messaged to - HIGHEST PRIORITY)
    2) Stored lead_phone_id in appointment_state
    3) Stored lead_phone_id in lead_appointment_state
    4) Environment variable fallback
    """
    # Try to get from appointment_state - check incoming_phone_id FIRST
    try:
        from controllers.web_socket import appointment_state
        st = appointment_state.get(wa_id) or {}

        # FIRST: Check incoming_phone_id - this is the number customer messaged to
        incoming_phone_id = st.get("incoming_phone_id")
        if incoming_phone_id:
            cfg = get_number_config(str(incoming_phone_id))
            if cfg and cfg.get("token"):
                display_num = re.sub(r"\D", "", cfg.get("name", "")) or "917729992376"
                print(f"[lead_auto_welcome] RESOLVED via incoming_phone_id: {incoming_phone_id} for wa_id={wa_id}")
                return cfg.get("token"), str(incoming_phone_id), display_num

        # Check lead_phone_id
        lead_phone_id = st.get("lead_phone_id")
        if lead_phone_id:
            cfg = get_number_config(str(lead_phone_id))
            if cfg and cfg.get("token"):
                display_num = re.sub(r"\D", "", cfg.get("name", "")) or "917729992376"
                print(f"[lead_auto_welcome] RESOLVED via lead_phone_id (appointment_state): {lead_phone_id} for wa_id={wa_id}")
                return cfg.get("token"), str(lead_phone_id), display_num
    except Exception:
        pass

    # Try to get from lead_appointment_state
    try:
        from controllers.web_socket import lead_appointment_state
        lst = lead_appointment_state.get(wa_id) or {}
        lead_phone_id = lst.get("lead_phone_id") or lst.get("phone_id")
        if lead_phone_id:
            cfg = get_number_config(str(lead_phone_id))
            if cfg and cfg.get("token"):
                display_num = re.sub(r"\D", "", cfg.get("name", "")) or "917729992376"
                print(f"[lead_auto_welcome] RESOLVED via lead_phone_id (lead_appointment_state): {lead_phone_id} for wa_id={wa_id}")
                return cfg.get("token"), str(lead_phone_id), display_num
    except Exception:
        pass

    # Fallback to environment variable
    env_pid = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    cfg = get_number_config(str(env_pid))
    if cfg and cfg.get("token"):
        display_num = re.sub(r"\D", "", cfg.get("name", "")) or os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
        print(f"[lead_auto_welcome] WARNING - FALLBACK to env phone_id: {env_pid} for wa_id={wa_id}")
        return cfg.get("token"), str(env_pid), display_num

    # Final fallback
    print(f"[lead_auto_welcome] WARNING - No valid phone_id found, using defaults for wa_id={wa_id}")
    return None, os.getenv("WHATSAPP_PHONE_ID", "367633743092037"), os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")


async def send_auto_welcome_message(db: Session, *, wa_id: str, phone_id_hint: Optional[str] = None) -> Dict[str, Any]:
    """Send the auto-welcome template message for appointment booking.
    
    Returns a status dict.
    """
    
    try:
        # Hard gate: do not send oliva_meta_ad when user is in Treatment Flow context
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            if bool(st.get("from_treatment_flow")) or bool(st.get("treatment_flow_phone_id")) or (st.get("flow_context") == "treatment"):
                print(f"[lead_appointment_flow] INFO - Skipping auto welcome for {wa_id}: in treatment flow context")
                return {"success": False, "skipped": True, "reason": "in_treatment_flow"}
        except Exception:
            pass

        # Resolve phone_id - use hint if provided, otherwise check state
        if phone_id_hint:
            cfg = get_number_config(str(phone_id_hint))
            if cfg and cfg.get("token"):
                access_token = cfg.get("token")
                phone_id = str(phone_id_hint)
                display_number = re.sub(r"\D", "", cfg.get("name", "")) or "917729992376"
                print(f"[lead_auto_welcome] RESOLVED via phone_id_hint: {phone_id} for wa_id={wa_id}")
            else:
                access_token, phone_id, display_number = _resolve_lead_phone_id(wa_id)
        else:
            access_token, phone_id, display_number = _resolve_lead_phone_id(wa_id)

        # Fallback to DB token if resolution failed
        if not access_token:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, "❌ Unable to send welcome message right now.", db)
                return {"success": False, "error": "no_token"}
            access_token = token_entry.token

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Send template message instead of interactive
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "template",
            "template": {
                "name": "oliva_meta_ad",
                "language": {"code": "en_US"}
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        if resp.status_code == 200:
            try:
                # Get message ID from response
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                
                # Get or create customer
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate
                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                
                # Save outbound message to database
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=display_number,
                    to_wa_id=wa_id,
                    type="template",
                    body="Template: oliva_meta_ad",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Auto welcome template message saved to database: {message_id}, from={display_number}")

                # Ensure flow state is set when template is sent (in case it wasn't set earlier)
                try:
                    from controllers.web_socket import lead_appointment_state
                    if wa_id not in lead_appointment_state:
                        lead_appointment_state[wa_id] = {}
                    lead_appointment_state[wa_id]["flow_context"] = "lead_appointment"
                    # Store the phone_id we used so subsequent messages use the same number
                    lead_appointment_state[wa_id]["lead_phone_id"] = phone_id
                    lead_appointment_state[wa_id]["lead_display_number"] = display_number
                    if "lead_source" not in lead_appointment_state[wa_id]:
                        lead_appointment_state[wa_id]["lead_source"] = "Facebook"
                    if "language" not in lead_appointment_state[wa_id]:
                        lead_appointment_state[wa_id]["language"] = "English"
                    print(f"[lead_appointment_flow] DEBUG - Ensured flow state is set for {wa_id} with lead_phone_id={phone_id}")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not set flow state: {e}")

                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": display_number,
                    "to": wa_id,
                    "type": "template",
                    "message": "Template: oliva_meta_ad",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "template_name": "oliva_meta_ad"
                    }
                })
                
                # Log last step reached: entry
                try:
                    from utils.flow_log import log_last_step_reached
                    from services.customer_service import get_customer_record_by_wa_id
                    _cust = get_customer_record_by_wa_id(db, wa_id)
                    log_last_step_reached(
                        db,
                        flow_type="lead_appointment",
                        step="entry",
                        wa_id=wa_id,
                        name=(getattr(_cust, "name", None) or "") if _cust else None,
                    )
                    print(f"[lead_appointment_flow] ✅ Logged last step: entry")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not log last step: {e}")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"success": True, "message_id": message_id}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send welcome message. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending welcome message: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_welcome_response(
    db: Session, 
    *, 
    wa_id: str, 
    reply_id: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle the response to the auto-welcome message.
    
    Args:
        reply_id: "yes_book_appointment", "not_now", or "book_appointment"
        
    Returns a status dict.
    """
    
    normalized_reply = (reply_id or "").strip().lower()
    
    if normalized_reply == "yes_book_appointment":
        # User wants to book - initialize flow state and proceed to city selection
        try:
            from controllers.web_socket import lead_appointment_state
            from controllers.web_socket import appointment_state
            from services.zoho_mapping_service import get_zoho_name
            if wa_id not in lead_appointment_state:
                lead_appointment_state[wa_id] = {}
            lead_appointment_state[wa_id]["flow_context"] = "lead_appointment"
            # Set default Zoho fields for lead appointment flow
            lead_appointment_state[wa_id]["lead_source"] = "Facebook"
            lead_appointment_state[wa_id]["language"] = "English"
            # Try to carry forward previously selected concern from appointment_state (treatment flow/referrer)
            try:
                st = appointment_state.get(wa_id) or {}
                prev_concern = st.get("selected_concern") or st.get("treatment_type") or st.get("treatment")
                if prev_concern:
                    lead_appointment_state[wa_id]["selected_concern"] = prev_concern
                    lead_appointment_state[wa_id]["zoho_mapped_concern"] = get_zoho_name(db, prev_concern)
                    print(f"[lead_appointment_flow] DEBUG - Carried forward concern into lead flow: {prev_concern}")
            except Exception as ce:
                print(f"[lead_appointment_flow] WARNING - Could not carry forward concern into lead flow: {ce}")
            print(f"[lead_appointment_flow] DEBUG - Initialized lead appointment state for {wa_id}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not initialize lead appointment state: {e}")
        
        from .city_selection import send_city_selection
        result = await send_city_selection(db, wa_id=wa_id)
        return {"status": "proceed_to_city_selection", "result": result}
    
    elif normalized_reply == "not_now":
        # User doesn't want to book now - send follow-up message with button
        return await send_not_now_followup(db, wa_id=wa_id, customer=customer)
    
    elif normalized_reply == "book_appointment":
        # User wants to book after "Not Now" - initialize flow state and proceed to city selection
        try:
            from controllers.web_socket import lead_appointment_state
            from controllers.web_socket import appointment_state
            from services.zoho_mapping_service import get_zoho_name
            if wa_id not in lead_appointment_state:
                lead_appointment_state[wa_id] = {}
            lead_appointment_state[wa_id]["flow_context"] = "lead_appointment"
            # Clear "Not Now" follow-up sequence flag since user wants to book now
            lead_appointment_state[wa_id].pop("not_now_followup_sequence", None)
            # Set default Zoho fields for lead appointment flow
            lead_appointment_state[wa_id]["lead_source"] = "Facebook"
            lead_appointment_state[wa_id]["language"] = "English"
            # Carry forward concern from previous appointment_state (e.g., from initial ad/referrer)
            try:
                st = appointment_state.get(wa_id) or {}
                prev_concern = st.get("selected_concern") or st.get("treatment_type") or st.get("treatment")
                if prev_concern:
                    lead_appointment_state[wa_id]["selected_concern"] = prev_concern
                    lead_appointment_state[wa_id]["zoho_mapped_concern"] = get_zoho_name(db, prev_concern)
                    print(f"[lead_appointment_flow] DEBUG - Carried forward concern into lead flow after Not Now: {prev_concern}")
            except Exception as ce:
                print(f"[lead_appointment_flow] WARNING - Could not carry forward concern after Not Now: {ce}")
            print(f"[lead_appointment_flow] DEBUG - Initialized lead appointment state for {wa_id}, cleared 'Not Now' follow-up sequence")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not initialize lead appointment state: {e}")
        
        from .city_selection import send_city_selection
        result = await send_city_selection(db, wa_id=wa_id)
        return {"status": "proceed_to_city_selection", "result": result}
    
    return {"status": "skipped"}


async def send_not_now_followup(db: Session, *, wa_id: str, customer: Any) -> Dict[str, Any]:
    """Send follow-up message with button when user clicks 'Not Now'.

    Returns a status dict.
    """

    try:
        # Resolve phone_id from state
        access_token, phone_id, display_number = _resolve_lead_phone_id(wa_id)

        # Fallback to DB token if resolution failed
        if not access_token:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, "❌ Unable to send message right now.", db)
                return {"success": False, "error": "no_token"}
            access_token = token_entry.token

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Send interactive message with button
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": "No problem! You can reach out anytime to schedule your appointment.\n\n✅ 8 lakh+ clients have trusted Oliva & experienced visible transformation\n\nWe'll be right here whenever you're ready to start your journey. 🌿"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "book_appointment", "title": "Book Appointment"}}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        if resp.status_code == 200:
            try:
                # Get message ID from response
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                
                # Save outbound message to database
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=display_number,
                    to_wa_id=wa_id,
                    type="interactive",
                    body="No problem! You can reach out anytime to schedule your appointment.\n\n✅ 8 lakh+ clients have trusted Oliva & experienced visible transformation\n\nWe'll be right here whenever you're ready to start your journey. 🌿",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Not Now followup message saved to database: {message_id}, from={display_number}")

                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": display_number,
                    "to": wa_id,
                    "type": "interactive",
                    "message": "No problem! You can reach out anytime to schedule your appointment.\n\n✅ 8 lakh+ clients have trusted Oliva & experienced visible transformation\n\nWe'll be right here whenever you're ready to start your journey. 🌿",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "buttons",
                        "options": ["Book Appointment"]
                    }
                })
                
                # Mark that we're in "Not Now" follow-up sequence
                try:
                    from controllers.web_socket import lead_appointment_state
                    if wa_id not in lead_appointment_state:
                        lead_appointment_state[wa_id] = {}
                    lead_appointment_state[wa_id]["not_now_followup_sequence"] = True
                    lead_appointment_state[wa_id]["flow_context"] = "lead_appointment"
                    print(f"[lead_appointment_flow] DEBUG - Marked 'Not Now' follow-up sequence for {wa_id}")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not mark 'Not Now' follow-up sequence: {e}")
                
                # Schedule Follow-Up 1 after sending "Not Now" message
                try:
                    import asyncio
                    from .follow_up1 import schedule_follow_up1_after_not_now
                    sent_at = datetime.now()
                    asyncio.create_task(schedule_follow_up1_after_not_now(wa_id, sent_at))
                    print(f"[lead_appointment_flow] DEBUG - Scheduled Follow-Up 1 after 'Not Now' message")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not schedule Follow-Up 1: {e}")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"success": True, "message_id": message_id, "status": "followup_sent"}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send message. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending message: {str(e)}", db)
        return {"success": False, "error": str(e)}
