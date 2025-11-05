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
        # Resolve credentials: prefer dedicated Treatment Flow number; fallback to legacy token/env
        phone_id_pref = os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WHATSAPP_PHONE_ID", "859830643878412")
        cfg = get_number_config(str(phone_id_pref)) if phone_id_pref else None
        if cfg and cfg.get("token"):
            access_token = cfg.get("token")
            phone_id = str(phone_id_pref)
        else:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, "❌ Unable to send city options right now.", db)
                return {"success": False, "error": "no_token"}
            access_token = token_entry.token
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "859830643878412")
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
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "859830643878412")

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

        # Use dedicated marketing number for all follow-ups
        try:
            _pid_hint = os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WELCOME_PHONE_ID") or os.getenv("WHATSAPP_PHONE_ID", "859830643878412")
        except Exception:
            _pid_hint = os.getenv("WHATSAPP_PHONE_ID", "859830643878412")
        await send_message_to_waid(wa_id, f"✅ Great! You selected {selected_city}.", db, phone_id_hint=str(_pid_hint))
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
                # Prefer mapped credentials for Treatment Flow number
                phone_id = os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WELCOME_PHONE_ID") or os.getenv("WHATSAPP_PHONE_ID", "859830643878412")
                cfg_env = get_number_config(str(phone_id)) if phone_id else None
                access_token = (cfg_env.get("token") if (cfg_env and cfg_env.get("token")) else token_entry.token)
                # After city selection, send mr_treatment template first unless already sent earlier
                try:
                    from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                    _st_appt = _appt_state.get(wa_id) or {}
                    already_sent_tpl = bool(_st_appt.get("mr_treatment_sent"))
                except Exception:
                    already_sent_tpl = False
                # Do NOT send mr_treatment here; only send concern buttons after city selection
                if False:
                    try:
                        from controllers.auto_welcome_controller import _send_template as _tpl
                        lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                        resp_tpl = _tpl(
                            wa_id=wa_id,
                            template_name="mr_treatment",
                            access_token=access_token,
                            phone_id=phone_id,
                            components=None,
                            lang_code=lang_code,
                        )
                        # Set flag immediately after sending to prevent duplicates
                        if resp_tpl.status_code == 200:
                            try:
                                from controllers.web_socket import appointment_state as _appt_state_mark  # type: ignore
                                _st_mark = _appt_state_mark.get(wa_id) or {}
                                _st_mark["mr_treatment_sent"] = True
                                _appt_state_mark[wa_id] = _st_mark
                                print(f"[city_selection] DEBUG - Set mr_treatment_sent flag for {wa_id}")
                            except Exception:
                                pass
                        try:
                            # Derive display from mapping for this phone_id
                            import re as _re
                            _cfg = get_number_config(str(phone_id))
                            _display_from = _re.sub(r"\D", "", (_cfg.get("name") or "")) if _cfg else os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                            await manager.broadcast({
                                "from": _display_from,
                                "to": wa_id,
                                "type": "template" if resp_tpl.status_code == 200 else "template_error",
                                "message": "mr_treatment sent" if resp_tpl.status_code == 200 else "mr_treatment failed",
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                    except Exception as _e:
                        try:
                            print(f"[city_selection] WARNING - mr_treatment send failed: {_e}")
                        except Exception:
                            pass
                else:
                    print(f"[city_selection] DEBUG - SKIP mr_treatment: already sent for {wa_id}")
                # Then send concern buttons
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
                try:
                    _resp_btn = _req.post(_gm(phone_id), headers=headers, json=payload_btn)
                    try:
                        print(f"[city_selection] DEBUG - concern buttons sent phone_id={phone_id} status={_resp_btn.status_code}")
                    except Exception:
                        pass
                except Exception as _e_btn:
                    print(f"[city_selection] ERROR - concern buttons post failed: {_e_btn}")
                # Broadcast to websocket for dashboard visibility
                try:
                    import re as _re
                    _cfg2 = get_number_config(str(phone_id))
                    _display_from2 = _re.sub(r"\D", "", (_cfg2.get("name") or "")) if _cfg2 else os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                    await manager.broadcast({
                        "from": _display_from2,
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
        # Send confirmation message for lead appointment flow
        await send_message_to_waid(wa_id, f"✅ Great! You selected {selected_city}.", db)
        
        from .clinic_location import send_clinic_location
        # Normalize city for clinic mapping (e.g., Bangalore -> Bengaluru)
        city_for_clinic = selected_city
        if selected_city == "Bangalore":
            city_for_clinic = "Bengaluru"
        result = await send_clinic_location(db, wa_id=wa_id, city=city_for_clinic)
        return {"status": "proceed_to_clinic_location", "city": selected_city, "result": result}
