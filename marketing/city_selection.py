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
from marketing.whatsapp_numbers import get_number_config
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager
from marketing.whatsapp_numbers import get_number_config


async def send_city_selection(db: Session, *, wa_id: str, phone_id_hint: str | None = None) -> Dict[str, Any]:
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
        # Resolve credentials: prefer explicit hint, then stored treatment_flow_phone_id, then env, then fallback
        phone_id = (str(phone_id_hint) if phone_id_hint else None)
        access_token = None
        
        # First priority: use provided phone_id_hint
        if phone_id:
            cfg = get_number_config(str(phone_id))
            if cfg and cfg.get("token"):
                access_token = cfg.get("token")
            else:
                phone_id = None
        # Second priority: Check stored phone_id from state - incoming_phone_id FIRST
        if not phone_id:
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                st = appointment_state.get(wa_id) or {}

                # FIRST: Check incoming_phone_id - this is the number customer messaged to
                incoming_phone_id = st.get("incoming_phone_id")
                if incoming_phone_id:
                    cfg = get_number_config(str(incoming_phone_id))
                    if cfg and cfg.get("token"):
                        access_token = cfg.get("token")
                        phone_id = str(incoming_phone_id)
                        print(f"[city_selection] RESOLVED via incoming_phone_id: {phone_id} for wa_id={wa_id}")

                # Check treatment_flow_phone_id
                if not phone_id:
                    stored_phone_id = st.get("treatment_flow_phone_id")
                    if stored_phone_id:
                        cfg = get_number_config(str(stored_phone_id))
                        if cfg and cfg.get("token"):
                            access_token = cfg.get("token")
                            phone_id = str(stored_phone_id)
                            print(f"[city_selection] RESOLVED via treatment_flow_phone_id: {phone_id} for wa_id={wa_id}")

                # If not found, check lead_phone_id
                if not phone_id:
                    lead_phone_id = st.get("lead_phone_id")
                    if lead_phone_id:
                        cfg = get_number_config(str(lead_phone_id))
                        if cfg and cfg.get("token"):
                            access_token = cfg.get("token")
                            phone_id = str(lead_phone_id)
                            print(f"[city_selection] RESOLVED via lead_phone_id: {phone_id} for wa_id={wa_id}")
            except Exception:
                pass
        # Also check lead_appointment_state
        if not phone_id:
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                lst = lead_appointment_state.get(wa_id) or {}
                lead_phone_id = lst.get("lead_phone_id") or lst.get("phone_id")
                if lead_phone_id:
                    cfg = get_number_config(str(lead_phone_id))
                    if cfg and cfg.get("token"):
                        access_token = cfg.get("token")
                        phone_id = str(lead_phone_id)
            except Exception:
                pass
        
        # Third priority: Env-configured treatment flow number
        if not phone_id:
            phone_id_pref = os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WELCOME_PHONE_ID")
            if phone_id_pref:
                cfg = get_number_config(str(phone_id_pref)) if phone_id_pref else None
                if cfg and cfg.get("token"):
                    access_token = cfg.get("token")
                    phone_id = str(phone_id_pref)
        
        # Final fallback: DB token + first allowed number
        if not phone_id:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, "❌ Unable to send city options right now.", db)
                return {"success": False, "error": "no_token"}
            access_token = token_entry.token
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            phone_id = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
        try:
            print(f"[city_selection] INFO - send_city_selection phone_id={phone_id} wa_id={wa_id}")
        except Exception:
            pass
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
                    from_wa_id=(
                        (lambda pid: (lambda cfg: __import__('re').sub(r"\D", "", (cfg.get("name") or "")) if cfg else None)(get_number_config(str(pid))))(phone_id)
                        or os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                    ),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Please select your city:",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                # Choose display "from" matching the phone_id we used to send
                try:
                    import re as _re
                    cfg = get_number_config(str(phone_id))
                    display_from = _re.sub(r"\D", "", (cfg.get("name") or "")) if cfg else os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                except Exception:
                    display_from = os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                await manager.broadcast({
                    "from": display_from,
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Please select your city:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Cities"}
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            try:
                from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                st_expect = _appt_state.get(wa_id) or {}
                st_expect["treatment_expect_interactive"] = "city_selection"
                _appt_state[wa_id] = st_expect
            except Exception:
                pass
            
            # Log last step reached: city_selection
            try:
                from utils.flow_log import log_last_step_reached
                log_last_step_reached(
                    db,
                    flow_type="treatment",
                    step="city_selection",
                    wa_id=wa_id,
                )
                print(f"[treatment_flow] ✅ Logged last step: city_selection")
            except Exception as e:
                print(f"[treatment_flow] WARNING - Could not log last step: {e}")
            
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
        
        # Use stored phone_id from treatment flow state OR lead flow state - check incoming_phone_id FIRST
        phone_id = None
        access_token = None
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}

            # FIRST: Check incoming_phone_id - this is the number customer messaged to
            incoming_phone_id = st.get("incoming_phone_id")
            if incoming_phone_id:
                cfg = get_number_config(str(incoming_phone_id))
                if cfg and cfg.get("token"):
                    access_token = cfg.get("token")
                    phone_id = str(incoming_phone_id)
                    print(f"[city_selection_page2] RESOLVED via incoming_phone_id: {phone_id} for wa_id={wa_id}")

            if not phone_id:
                stored_phone_id = st.get("treatment_flow_phone_id")
                if stored_phone_id:
                    cfg = get_number_config(str(stored_phone_id))
                    if cfg and cfg.get("token"):
                        access_token = cfg.get("token")
                        phone_id = str(stored_phone_id)
                        print(f"[city_selection_page2] RESOLVED via treatment_flow_phone_id: {phone_id} for wa_id={wa_id}")
            # If not found, check lead_phone_id
            if not phone_id:
                lead_phone_id = st.get("lead_phone_id")
                if lead_phone_id:
                    cfg = get_number_config(str(lead_phone_id))
                    if cfg and cfg.get("token"):
                        access_token = cfg.get("token")
                        phone_id = str(lead_phone_id)
                        print(f"[city_selection_page2] RESOLVED via lead_phone_id: {phone_id} for wa_id={wa_id}")
        except Exception:
            pass
        # Also check lead_appointment_state
        if not phone_id:
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                lst = lead_appointment_state.get(wa_id) or {}
                lead_phone_id = lst.get("lead_phone_id") or lst.get("phone_id")
                if lead_phone_id:
                    cfg = get_number_config(str(lead_phone_id))
                    if cfg and cfg.get("token"):
                        access_token = cfg.get("token")
                        phone_id = str(lead_phone_id)
                        print(f"[city_selection_page2] RESOLVED via lead_phone_id (lead_state): {phone_id} for wa_id={wa_id}")
            except Exception:
                pass

        if not phone_id:
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            phone_id = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
            print(f"[city_selection_page2] WARNING - FALLBACK to first allowed: {phone_id} for wa_id={wa_id}")

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
    """Handle city selection response for treatment flow.
    
    Args:
        reply_id: City ID like "city_hyderabad", "city_bengaluru", etc.
        
    Returns a status dict.
    """
    
    # Clear interactive expectation since user responded
    try:
        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
        st_clear = _appt_state.get(wa_id) or {}
        st_clear.pop("treatment_expect_interactive", None)
        _appt_state[wa_id] = st_clear
    except Exception:
        pass

    # CRITICAL: Only handle city selection if this is actually a treatment flow
    # Skip if this is a lead appointment flow number to prevent overlap
    try:
        from controllers.components.lead_appointment_flow.config import LEAD_APPOINTMENT_PHONE_ID, LEAD_APPOINTMENT_DISPLAY_LAST10
        from controllers.web_socket import appointment_state  # type: ignore
        st_ctx = appointment_state.get(wa_id) or {}
        flow_ctx = st_ctx.get("flow_context")
        
        # If explicitly in lead appointment flow, skip (let lead appointment handler process it)
        if flow_ctx == "lead_appointment":
            print(f"[marketing/city_selection] DEBUG - Skipping city selection: in lead appointment flow context")
            return {"status": "skipped", "reason": "lead_appointment_flow_context"}
    except Exception as e:
        print(f"[marketing/city_selection] WARNING - Could not verify flow context: {e}")
    
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
        # Use stored phone_id from treatment flow state OR lead flow state - check incoming_phone_id FIRST
        phone_id_hint = None
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}

            # FIRST: Check incoming_phone_id - this is the number customer messaged to
            incoming_phone_id = st.get("incoming_phone_id")
            if incoming_phone_id:
                phone_id_hint = str(incoming_phone_id)
                print(f"[city_selection] RESOLVED via incoming_phone_id for invalid: {phone_id_hint} for wa_id={wa_id}")

            if not phone_id_hint:
                stored_phone_id = st.get("treatment_flow_phone_id")
                if stored_phone_id:
                    phone_id_hint = stored_phone_id
            # If not found, check lead_phone_id
            if not phone_id_hint:
                lead_phone_id = st.get("lead_phone_id")
                if lead_phone_id:
                    phone_id_hint = lead_phone_id
        except Exception:
            pass
        # Also check lead_appointment_state
        if not phone_id_hint:
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                lst = lead_appointment_state.get(wa_id) or {}
                lead_phone_id = lst.get("lead_phone_id") or lst.get("phone_id")
                if lead_phone_id:
                    phone_id_hint = lead_phone_id
            except Exception:
                pass

        if not phone_id_hint:
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]

        await send_message_to_waid(wa_id, "❌ Invalid city selection. Please try again.", db, phone_id_hint=str(phone_id_hint))
        return {"status": "invalid_selection"}
    
    # Store selected city in customer data or session and establish idempotency keys
    try:
        from controllers.web_socket import lead_appointment_state, appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        # Soft idempotency: only skip if same reply_id AND topics were sent AND mr_treatment was sent (within last 60s)
        last_city_reply = lead_appointment_state[wa_id].get("last_city_reply_id")
        topics_sent = lead_appointment_state[wa_id].get("treatment_topics_sent")
        if last_city_reply == (reply_id or "").strip().lower() and topics_sent:
            # Check if mr_treatment was actually sent
            try:
                from controllers.web_socket import appointment_state as _appt_check
                mr_sent = bool((_appt_check.get(wa_id) or {}).get("mr_treatment_sent"))
                if mr_sent:
                    # Check timestamp - only block if sent very recently (within 60 seconds)
                    topics_ts = lead_appointment_state[wa_id].get("topics_sent_ts")
                    if topics_ts:
                        try:
                            from datetime import datetime as _dt_check
                            ts_obj = _dt_check.fromisoformat(topics_ts) if isinstance(topics_ts, str) else None
                            if ts_obj and (_dt_check.now() - ts_obj).total_seconds() < 60:
                                return {"status": "city_already_handled", "city": selected_city}
                        except Exception:
                            pass
            except Exception:
                pass

        lead_appointment_state[wa_id]["last_city_reply_id"] = (reply_id or "").strip().lower()
        lead_appointment_state[wa_id]["selected_city"] = selected_city
        print(f"[lead_appointment_flow] DEBUG - Stored city selection: {selected_city}")
        # Also mirror selected_city into appointment_state for treatment flow paths
        try:
            if 'appointment_state' not in globals():
                from controllers.web_socket import appointment_state  # type: ignore
            _appt_state = appointment_state  # type: ignore
            st_city = _appt_state.get(wa_id) or {}
            st_city["selected_city"] = selected_city
            _appt_state[wa_id] = st_city
            print(f"[lead_appointment_flow] DEBUG - Mirrored city into appointment_state: {selected_city}")
        except Exception as e_city_mirror:
            print(f"[lead_appointment_flow] WARNING - Could not mirror city into appointment_state: {e_city_mirror}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not store city selection: {e}")
    
    # Determine flow context
    # Priority: Check lead_appointment_state first (for lead appointment flow), then appointment_state (for treatment flow)
    context = None
    try:
        from controllers.web_socket import lead_appointment_state as _lead_state
        context = ((_lead_state.get(wa_id) or {}).get("flow_context"))
    except Exception:
        context = None
    if not context:
        try:
            from controllers.web_socket import appointment_state as _appt_state
            context = ((_appt_state.get(wa_id) or {}).get("flow_context"))
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

        # Use stored phone_id from treatment flow state OR lead flow state - check incoming_phone_id FIRST
        phone_id_hint = None
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}

            # FIRST: Check incoming_phone_id - this is the number customer messaged to
            incoming_phone_id = st.get("incoming_phone_id")
            if incoming_phone_id:
                phone_id_hint = str(incoming_phone_id)
                print(f"[city_selection] RESOLVED via incoming_phone_id for treatment: {phone_id_hint} for wa_id={wa_id}")

            # Check treatment_flow_phone_id
            if not phone_id_hint:
                stored_phone_id = st.get("treatment_flow_phone_id")
                if stored_phone_id:
                    phone_id_hint = stored_phone_id
            # If not found, check lead_phone_id (for lead appointment flow triggering treatment)
            if not phone_id_hint:
                lead_phone_id = st.get("lead_phone_id")
                if lead_phone_id:
                    phone_id_hint = lead_phone_id
        except Exception:
            pass

        # Also check lead_appointment_state
        if not phone_id_hint:
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                lst = lead_appointment_state.get(wa_id) or {}
                lead_phone_id = lst.get("lead_phone_id") or lst.get("phone_id")
                if lead_phone_id:
                    phone_id_hint = lead_phone_id
            except Exception:
                pass

        if not phone_id_hint:
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
            print(f"[city_selection] WARNING - No stored phone_id, falling back to first allowed: {phone_id_hint}")

        try:
            print(f"[city_selection] INFO - treatment city handled wa_id={wa_id} city={selected_city} phone_id_hint={phone_id_hint}")
        except Exception:
            pass
        try:
            # Early exit only if topics were sent AND mr_treatment was sent (within last 60s)
            try:
                from controllers.web_socket import lead_appointment_state as _lead_state_early, appointment_state as _appt_early
                st_early = _lead_state_early.get(wa_id) or {}
                topics_sent_early = st_early.get("treatment_topics_sent")
                if topics_sent_early:
                    # Check if mr_treatment was actually sent
                    mr_sent_early = bool((_appt_early.get(wa_id) or {}).get("mr_treatment_sent"))
                    if mr_sent_early:
                        # Check timestamp - only block if sent very recently
                        topics_ts_early = st_early.get("topics_sent_ts")
                        if topics_ts_early:
                            try:
                                from datetime import datetime as _dt_early
                                ts_obj_early = _dt_early.fromisoformat(topics_ts_early) if isinstance(topics_ts_early, str) else None
                                if ts_obj_early and (_dt_early.now() - ts_obj_early).total_seconds() < 60:
                                    # release lock and exit
                                    st_early["treatment_topics_lock"] = False
                                    _lead_state_early[wa_id] = st_early
                                    return {"status": "topics_already_sent", "city": selected_city}
                            except Exception:
                                pass
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

            # Step 3: Send mr_treatment template after city selection
            try:
                from marketing.interactive import send_mr_treatment  # type: ignore
                # Check if mr_treatment was already sent to prevent duplicates
                try:
                    from controllers.web_socket import appointment_state as _appt_mr
                    st_mr = _appt_mr.get(wa_id) or {}
                    mr_sent = bool(st_mr.get("mr_treatment_sent"))
                    if not mr_sent:
                        _ = send_mr_treatment(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
                        print(f"[city_selection] DEBUG - Sent mr_treatment template for wa_id={wa_id}")
                    else:
                        print(f"[city_selection] DEBUG - Skipping mr_treatment template (already sent)")
                except Exception:
                    _ = send_mr_treatment(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
            except Exception as _e_mr:
                print(f"[city_selection] WARNING - Could not send mr_treatment template: {_e_mr}")
            
            # Step 4: Send concern buttons after mr_treatment template
            try:
                from marketing.interactive import send_concern_buttons  # type: ignore
                # Send "Please choose your area of concern:" message before concern buttons
                # await send_message_to_waid(wa_id, "Please choose your area of concern:", db, phone_id_hint=str(phone_id_hint))
                # Then send concern buttons (only if not already sent)
                try:
                    from controllers.web_socket import appointment_state as _appt_concern
                    st_concern = _appt_concern.get(wa_id) or {}
                    concern_sent = bool(st_concern.get("concern_buttons_sent"))
                    if not concern_sent:
                        _ = send_concern_buttons(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
                    else:
                        print(f"[city_selection] DEBUG - Skipping concern buttons (already sent)")
                except Exception:
                    _ = send_concern_buttons(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
            except Exception as _e_int:
                print(f"[city_selection] WARNING - interactive senders failed: {_e_int}")
            
            # CRITICAL: After city selection + mr_treatment + concern buttons, flow is now STARTED
            # Mark flow as started and schedule first follow-up
            try:
                from controllers.web_socket import appointment_state as _appt_started  # type: ignore
                st_started = _appt_started.get(wa_id) or {}
                st_started["flow_started"] = True  # Mark flow as started (after welcome + city)
                _appt_started[wa_id] = st_started
                print(f"[city_selection] DEBUG - Flow marked as started for wa_id={wa_id}")
                
                # Schedule first follow-up now that flow has started
                try:
                    from services.followup_service import schedule_next_followup
                    from services.customer_service import get_or_create_customer
                    from schemas.customer_schema import CustomerCreate
                    customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                    schedule_next_followup(db, customer_id=customer.id, delay_minutes=5, stage_label="flow_started")
                    print(f"[city_selection] DEBUG - Scheduled first follow-up for wa_id={wa_id} (flow started)")
                except Exception as e_fu:
                    print(f"[city_selection] WARNING - Could not schedule follow-up: {e_fu}")
            except Exception as e_start:
                print(f"[city_selection] WARNING - Could not mark flow as started: {e_start}")
            
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

    # Non-treatment contexts are not handled in marketing flow
    return {"status": "ignored_non_treatment", "city": selected_city}