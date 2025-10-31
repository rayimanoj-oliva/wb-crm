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
                    body="Please select your city:",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Please select your city:",
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
    
    # Store selected city in customer data or session and establish idempotency keys
    try:
        from controllers.web_socket import lead_appointment_state, appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        # Hard idempotency: if this same reply_id already handled and topics were sent, skip
        last_city_reply = lead_appointment_state[wa_id].get("last_city_reply_id")
        if last_city_reply == (reply_id or "").strip().lower() and lead_appointment_state[wa_id].get("treatment_topics_sent"):
            return {"status": "city_already_handled", "city": selected_city}

        lead_appointment_state[wa_id]["last_city_reply_id"] = (reply_id or "").strip().lower()
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

    # Treatment flow: after city, send mr_treatment (once) then ask concern (Skin/Hair/Body)
    if context == "treatment":
        # Strong re-entrancy lock: prevent duplicate sends if handler is invoked twice concurrently or reprocessed
        try:
            from controllers.web_socket import lead_appointment_state as _lead_lock  # type: ignore
            lock_state = _lead_lock.get(wa_id) or {}
            from datetime import datetime as _dt
            now = _dt.now()
            lock_ts = lock_state.get("treatment_topics_lock_ts")
            lock_flag = bool(lock_state.get("treatment_topics_lock"))
            if lock_flag and isinstance(lock_ts, str):
                try:
                    from datetime import datetime as _dt2
                    if (now - _dt2.fromisoformat(lock_ts)).total_seconds() < 30:
                        return {"status": "topics_locked_skip", "city": selected_city}
                except Exception:
                    return {"status": "topics_locked_skip", "city": selected_city}
            # acquire lock
            lock_state["treatment_topics_lock"] = True
            lock_state["treatment_topics_lock_ts"] = now.isoformat()
            _lead_lock[wa_id] = lock_state
        except Exception:
            pass

        await send_message_to_waid(wa_id, f"✅ Great! You selected {selected_city}.", db)
        try:
            # Early exit if already marked sent
            try:
                from controllers.web_socket import lead_appointment_state as _lead_state_early
                st_early = _lead_state_early.get(wa_id) or {}
                if st_early.get("treatment_topics_sent"):
                    # release lock and exit
                    st_early["treatment_topics_lock"] = False
                    _lead_state_early[wa_id] = st_early
                    return {"status": "topics_already_sent", "city": selected_city}
            except Exception:
                pass

            # Idempotency: avoid duplicate mr_treatment/template and topic sends within a short window
            try:
                from controllers.web_socket import lead_appointment_state as _lead_state  # type: ignore
                st = _lead_state.get(wa_id) or {}
                from datetime import datetime as _dt
                now = _dt.now()
                # Template guard
                tpl_ts = st.get("treatment_template_ts")
                tpl_sent = bool(st.get("treatment_template_sent"))
                if tpl_sent and isinstance(tpl_ts, str):
                    try:
                        from datetime import datetime as _dt2
                        if (now - _dt2.fromisoformat(tpl_ts)).total_seconds() < 10:
                            skip_template = True
                        else:
                            skip_template = False
                    except Exception:
                        skip_template = True
                else:
                    skip_template = False
                # Topics guard
                topics_ts = st.get("topics_sent_ts")
                topics_sent = bool(st.get("treatment_topics_sent"))
                if topics_sent and isinstance(topics_ts, str):
                    try:
                        from datetime import datetime as _dt3
                        if (now - _dt3.fromisoformat(topics_ts)).total_seconds() < 5:
                            return {"status": "topics_already_sent_recently", "city": selected_city}
                    except Exception:
                        return {"status": "topics_already_sent_recently", "city": selected_city}
            except Exception:
                skip_template = False

            token_entry = get_latest_token(db)
            if token_entry and token_entry.token:
                access_token = token_entry.token
                phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                from controllers.auto_welcome_controller import _send_template  # reuse helper
                tpl_ok = False
                if not skip_template:
                    try:
                        resp_tpl = _send_template(
                            wa_id=wa_id,
                            template_name="mr_treatment",
                            access_token=access_token,
                            phone_id=phone_id,
                            components=None,
                            lang_code=lang_code,
                        )
                        tpl_ok = bool(getattr(resp_tpl, "status_code", None) == 200)
                    except Exception:
                        tpl_ok = False
                    if tpl_ok:
                        # Mark template sent and release lock; do NOT send interactive
                        try:
                            from controllers.web_socket import lead_appointment_state as _lead_state_tpl
                            st_tpl = _lead_state_tpl.get(wa_id) or {}
                            st_tpl["treatment_template_sent"] = True
                            st_tpl["treatment_template_ts"] = datetime.now().isoformat()
                            st_tpl["treatment_topics_lock"] = False
                            _lead_state_tpl[wa_id] = st_tpl
                        except Exception:
                            pass
                        return {"status": "treatment_template_sent", "city": selected_city}
                # If template skipped or failed, send concern buttons once
                try:
                    from controllers.web_socket import lead_appointment_state as _lead_state_mark
                    st_mark = _lead_state_mark.get(wa_id) or {}
                    # If already marked sent, avoid sending again
                    if st_mark.get("treatment_topics_sent"):
                        st_mark["treatment_topics_lock"] = False
                        _lead_state_mark[wa_id] = st_mark
                        return {"status": "topics_already_sent", "city": selected_city}
                    st_mark["treatment_topics_sent"] = True
                    st_mark["topics_sent_ts"] = datetime.now().isoformat()
                    _lead_state_mark[wa_id] = st_mark
                except Exception:
                    pass
                headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
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
                                {"type": "reply", "reply": {"id": "body", "title": "Body"}},
                            ]
                        },
                    },
                }
                import requests as _req
                from config.constants import get_messages_url as _gm
                _req.post(_gm(phone_id), headers=headers, json=payload_btn)
                # Broadcast to websocket for dashboard visibility
                try:
                    await manager.broadcast({
                        "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                        "to": wa_id,
                        "type": "interactive",
                        "message": "Please choose your area of concern:",
                        "timestamp": datetime.now().isoformat(),
                        "meta": {"kind": "buttons", "options": ["Skin", "Hair", "Body"]}
                    })
                except Exception:
                    pass
                # release lock
                try:
                    from controllers.web_socket import lead_appointment_state as _lead_unlock
                    st_unlock = _lead_unlock.get(wa_id) or {}
                    st_unlock["treatment_topics_lock"] = False
                    _lead_unlock[wa_id] = st_unlock
                except Exception:
                    pass
                return {"status": "treatment_topics_sent", "city": selected_city}
                # release lock
                try:
                    from controllers.web_socket import lead_appointment_state as _lead_unlock
                    st_unlock = _lead_unlock.get(wa_id) or {}
                    st_unlock["treatment_topics_lock"] = False
                    _lead_unlock[wa_id] = st_unlock
                except Exception:
                    pass
                return {"status": "treatment_topics_sent", "city": selected_city}
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not send treatment topics: {e}")
            # release lock on failure
            try:
                from controllers.web_socket import lead_appointment_state as _lead_unlock2
                st_unlock2 = _lead_unlock2.get(wa_id) or {}
                st_unlock2["treatment_topics_lock"] = False
                _lead_unlock2[wa_id] = st_unlock2
            except Exception:
                pass
        return {"status": "failed_to_send_topics", "city": selected_city}

    # Lead appointment flow: proceed to clinic selection
    else:
        from .clinic_location import send_clinic_location
        # Normalize city for clinic mapping (e.g., Bangalore -> Bengaluru)
        city_for_clinic = selected_city
        if selected_city == "Bangalore":
            city_for_clinic = "Bengaluru"
        result = await send_clinic_location(db, wa_id=wa_id, city=city_for_clinic)
        return {"status": "proceed_to_clinic_location", "city": selected_city, "result": result}
