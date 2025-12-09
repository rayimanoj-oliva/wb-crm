from __future__ import annotations

from datetime import datetime
from typing import Optional, Any, Dict

import os
import re
import requests

from sqlalchemy.orm import Session

from services.whatsapp_service import get_latest_token
from marketing.whatsapp_numbers import get_number_config, WHATSAPP_NUMBERS
from config.constants import get_messages_url
from utils.ws_manager import manager
from utils.whatsapp import send_message_to_waid


def _safe_debug(prefix: str, **fields: Any) -> None:
    """Best-effort structured debug printer; never raises."""
    try:
        import json as _json  # local import to avoid global cost

        payload = {
            "ts": datetime.utcnow().isoformat(),
            "prefix": prefix,
            **fields,
        }
        print(f"[treatment_flow] DEBUG {prefix} { _json.dumps(payload, default=str) }")
    except Exception:
        # Last-resort plain print; ignore all errors
        try:
            print(f"[treatment_flow] DEBUG {prefix} {fields}")
        except Exception:
            pass


async def run_treament_flow(
    db: Session,
    *,
    message_type: str,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    body_text: str,
    timestamp: datetime,
    customer: Any,
    wa_id: str,
    value: Dict[str, Any] | None,
    sender_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Encapsulates the text message auto-welcome validation and treatment template flow.

    Returns a status dict. This function is safe to call for any message type; it
    will act only when `message_type == "text"`.
    """

    # Log entry event for observability
    try:
        from utils.flow_log import log_flow_event  # type: ignore
        log_flow_event(
            db,
            flow_type="treatment",
            step="entry",
            wa_id=wa_id,
            description="Treatment flow invoked",
        )
    except Exception:
        pass

    handled_text = False

    # 1) Do NOT persist/broadcast inbound text here to avoid duplicates.
    #    The main webhook controller handles saving + broadcasting once.
    #    Continue with flow analysis only.
    if message_type == "text":
        pass

        # 2) Normalize body text for consistent comparison
        def _normalize(txt: str) -> str:
            if not txt:
                return ""
            try:
                # Replace fancy apostrophes/quotes with plain, collapse spaces
                txt = txt.replace("'", "'").replace("“", '"').replace("”", '"')
                txt = txt.lower().strip()
                txt = re.sub(r"\s+", " ", txt)
                return txt
            except Exception:
                return txt.lower().strip()

        normalized_body = _normalize(body_text)
        _safe_debug(
            "incoming_text",
            wa_id=wa_id,
            message_id=message_id,
            raw_body=body_text,
            normalized_body=normalized_body,
        )

        # 3) Prefill detection for treatment welcome message
        # Rule: trigger ONLY when this looks like the *start* of a treatment conversation,
        # Check if customer is in treatment flow - allow access from BOTH treatment flow numbers
        # Customers should be able to switch between 7617613030 and 8297882978
        
        # CRITICAL: Check if flow was completed - if customer sends a new message, restart the flow
        try:
            from controllers.web_socket import appointment_state as _appt_state_restart  # type: ignore
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS  # type: ignore
            st_restart = _appt_state_restart.get(wa_id) or {}
            flow_completed = bool(st_restart.get("flow_completed"))
            
            # Check if customer is messaging a treatment flow number
            phone_id_meta_restart = ((value or {}).get("metadata", {}) or {}).get("phone_number_id")
            is_treatment_number = False
            if phone_id_meta_restart and str(phone_id_meta_restart) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                is_treatment_number = True
            elif to_wa_id:
                import re as _re_restart
                from marketing.whatsapp_numbers import WHATSAPP_NUMBERS  # type: ignore
                disp_digits_restart = _re_restart.sub(r"\D", "", str(to_wa_id))
                disp_last10_restart = disp_digits_restart[-10:] if len(disp_digits_restart) >= 10 else disp_digits_restart
                for pid_restart in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                    cfg_restart = WHATSAPP_NUMBERS.get(pid_restart) if isinstance(WHATSAPP_NUMBERS, dict) else None
                    if cfg_restart:
                        name_digits_restart = _re_restart.sub(r"\D", "", (cfg_restart.get("name") or ""))
                        name_last10_restart = name_digits_restart[-10:] if len(name_digits_restart) >= 10 else name_digits_restart
                        if name_last10_restart and disp_last10_restart and name_last10_restart == disp_last10_restart:
                            is_treatment_number = True
                            break
            
            # If flow was completed and customer sends a new message to treatment number, restart flow
            if flow_completed and is_treatment_number and bool(normalized_body):
                print(f"[treatment_flow] DEBUG - Flow was completed, but customer sent new message. Restarting flow for wa_id={wa_id}")
                # Clear all flow state to restart from beginning
                st_restart.pop("flow_completed", None)
                st_restart.pop("treatment_welcome_sent", None)
                st_restart.pop("treatment_welcome_sending_ts", None)
                st_restart.pop("treatment_expect_interactive", None)
                st_restart.pop("mr_treatment_sent", None)
                st_restart.pop("concern_buttons_sent", None)
                st_restart.pop("flow_started", None)
                st_restart.pop("error_prompt_sent_timestamp", None)
                # Keep flow_context and phone_id so flow can restart
                _appt_state_restart[wa_id] = st_restart
                
                # Also clear related state in lead_appointment_state if present
                try:
                    from controllers.web_socket import lead_appointment_state  # type: ignore
                    lst_restart = lead_appointment_state.get(wa_id) or {}
                    lst_restart.pop("treatment_topics_sent", None)
                    lst_restart.pop("topics_sent_ts", None)
                    lst_restart.pop("treatment_topics_lock", None)
                    lst_restart.pop("treatment_topics_lock_ts", None)
                    lst_restart.pop("treatment_template_sent", None)
                    lst_restart.pop("treatment_template_ts", None)
                    lst_restart.pop("last_city_reply_id", None)
                    lst_restart.pop("selected_city", None)
                    lst_restart.pop("selected_concern", None)
                    lead_appointment_state[wa_id] = lst_restart
                    print(f"[treatment_flow] DEBUG - Cleared lead_appointment_state for flow restart: wa_id={wa_id}")
                except Exception as e_lead_clear:
                    print(f"[treatment_flow] WARNING - Could not clear lead_appointment_state: {e_lead_clear}")
        except Exception as e_restart:
            print(f"[treatment_flow] WARNING - Could not check/clear flow_completed state: {e_restart}")
        
        in_active_treatment_flow = False
        already_welcome_sent = False
        is_current_number_treatment = False
        try:
            from controllers.web_socket import appointment_state as _appt_state  # type: ignore
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS  # type: ignore
            st_now = _appt_state.get(wa_id) or {}
            flow_ctx = st_now.get("flow_context")
            expect_step = st_now.get("treatment_expect_interactive")
            already_welcome_sent = bool(st_now.get("treatment_welcome_sent"))  # Use treatment-specific flag
            stored_phone_id = st_now.get("treatment_flow_phone_id")
            
            # Check if customer is in treatment flow context (has already started flow)
            is_in_treatment_context = (flow_ctx == "treatment") or bool(expect_step) or already_welcome_sent
            
            # Also check if the CURRENT incoming number is a treatment flow number
            # This allows customers to switch between treatment flow numbers
            phone_id_meta = ((value or {}).get("metadata", {}) or {}).get("phone_number_id")
            if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                is_current_number_treatment = True
            elif to_wa_id:
                # Check by display number
                import re as _re
                from marketing.whatsapp_numbers import WHATSAPP_NUMBERS  # type: ignore
                disp_digits = _re.sub(r"\D", "", str(to_wa_id))
                disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                for pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                    cfg = WHATSAPP_NUMBERS.get(pid) if isinstance(WHATSAPP_NUMBERS, dict) else None
                    if cfg:
                        name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                        name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                        if name_last10 and disp_last10 and name_last10 == disp_last10:
                            is_current_number_treatment = True
                            break
            
            # Customer is in active treatment flow if:
            # 1. They're in treatment context (from previous message) AND have already received welcome
            # This prevents sending welcome again if they're already in the flow
            in_active_treatment_flow = is_in_treatment_context and already_welcome_sent
            
            # If customer is messaging a treatment flow number but stored phone_id is different, update it
            # This allows customers to switch between 7617613030 and 8297882978
            if is_current_number_treatment and phone_id_meta and str(phone_id_meta) != str(stored_phone_id):
                st_now["treatment_flow_phone_id"] = str(phone_id_meta)
                st_now["incoming_phone_id"] = str(phone_id_meta)
                st_now["flow_context"] = "treatment"
                st_now["from_treatment_flow"] = True
                _appt_state[wa_id] = st_now
                print(f"[treatment_flow] DEBUG - Updated treatment_flow_phone_id from {stored_phone_id} to {phone_id_meta} for wa_id={wa_id} (customer switched numbers)")
        except Exception:
            in_active_treatment_flow = False

        # Resolve phone_id hint for replies (treatment numbers only)
        phone_id_hint = None
        try:
            if 'phone_id_meta' in locals() and phone_id_meta:
                phone_id_hint = str(phone_id_meta)
            elif 'st_now' in locals() and isinstance(st_now, dict):
                phone_id_hint = st_now.get("treatment_flow_phone_id") or st_now.get("incoming_phone_id")
        except Exception:
            phone_id_hint = None

        # Quick auto-replies for consultation fees and job/vacancy queries
        # HARD GATE: only if incoming number is one of the treatment numbers (by phone_id or display)
        is_allowed_treatment = False
        try:
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            allowed_display_last10 = {"7617613030", "8297882978"}
            if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                is_allowed_treatment = True
            elif to_wa_id:
                import re as _re
                disp_digits = _re.sub(r"\D", "", str(to_wa_id))
                disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                if disp_last10 in allowed_display_last10:
                    is_allowed_treatment = True
        except Exception:
            is_allowed_treatment = False

        if is_allowed_treatment:
            try:
                # Split detection into consultation-fee vs treatment-pricing so we can respond with the correct copy
                consult_keywords = [
    # Consultation related
    "consultation fee", "consultation fees", "consultation charge", "consultation charges",
    "consultation cost", "consultation", "consultations",
    "consult fee", "consult fees", "consult cost", "consult charge",
    "consulting fee", "consulting charges", "consulting cost",

    # Generic fee/charge terms (could be ambiguous, keep here for consultation default)
    "fee", "fees", "charge", "charges", "cost", "price", "amount",

    # Common consultation questions
    "how much for consultation",
    "what is your fee", "your charges", "price details",
    "consultation price", "session fee",
    "appointment fee", "appointment charges",

    # Informal / chat variations
    "fee ah", "fees ah", "charges ah", "cost ah",
    "how much u charge", "how much do you charge",
    "what's your charges", "what's your fees",
    "consultation amount",
]

                treatment_price_keywords = [
    # Treatment / service pricing
    "treatment cost", "treatment charges", "treatment fee",
    "procedure cost", "procedure charges", "service charge",
    "service cost", "cost of treatment", "price of treatment",
    "treatment price", "treatment amount","treatment","treatments"
    "how much for treatment",
]

                # Generic questions we want to deflect to structured options
                doctor_location_keywords = [
    # Doctor availability / generic availability
    "doctor availability", "doctor available", "is doctor available", "doctor today", "available doctor",
    "dermatologist available", "doctor timings", "doctor time", "doctor schedule",
    # Location / clinic
    "location", "locations", "clinic", "clinics", "center", "centre", "branch", "branches",
    "nearest clinic", "nearest branch", "nearest center", "nearest centre", "where are you", "where are you located",
    "address", "location please", "clinic address",
    # Medicines / prescriptions
    "medicine", "medicines", "medication", "prescription", "drug", "drugs",
    "ointment", "tablet", "tablets", "capsule", "capsules", "cream",
]

                job_keywords = [
    # Base terms
    "job", "jobs", "vacancy", "vacancies", "career", "careers",
    "hiring", "recruitment", "recruiting", "job opening",
    "job openings", "job opportunity", "opportunities",
    
    # Role inquiry terms
    "any openings", "any vacancy", "any job", "any hiring",
    "looking for job", "job application", "apply for job",
    "vacancy in the clinic", "vacancy in clinic", "vacancy at clinic",
    "vacancy for ot", "ot vacancy", "ot staff", "ot nurse", "ot assistant",
    "clinic vacancy", "hospital vacancy",
    
    # HR terms
    "hr", "human resources", "walk-in", "walkin", "interview",
    "interviews", "job interview", "schedule interview",
    
    # Informal phrases
    "job aa", "vacancy aa", "hiring ah", "any job available",
    "any positions", "open positions", "open roles",
    "any vacancy in ot", "any vacancy in clinic",
]


                # Resolve the correct treatment phone_id and from_wa_id for replies; if missing, fall back to first allowed treatment number (never lead number)
                treatment_phone_id = None
                treatment_from_wa = None
                try:
                    from marketing.whatsapp_numbers import WHATSAPP_NUMBERS, TREATMENT_FLOW_ALLOWED_PHONE_IDS
                    # 1) Use incoming phone_id if allowed
                    if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                        treatment_phone_id = str(phone_id_meta)
                        cfg_in = WHATSAPP_NUMBERS.get(str(phone_id_meta)) if isinstance(WHATSAPP_NUMBERS, dict) else None
                        if cfg_in:
                            import re as _re
                            treatment_from_wa = _re.sub(r"\D", "", cfg_in.get("name", "")) or None
                    # 2) Else match display number to allowed treatment numbers
                    elif to_wa_id:
                        import re as _re
                        disp_digits = _re.sub(r"\D", "", str(to_wa_id))
                        disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                        for pid, cfg in (WHATSAPP_NUMBERS or {}).items():
                            if pid not in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                continue
                            name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                            name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                            if name_last10 and disp_last10 and name_last10 == disp_last10:
                                treatment_phone_id = str(pid)
                                treatment_from_wa = name_digits or None
                                break
                    # 3) Fallback to first allowed treatment phone_id (never lead number)
                    if not treatment_phone_id and TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                        treatment_phone_id = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                        cfg_fb = WHATSAPP_NUMBERS.get(str(treatment_phone_id)) if isinstance(WHATSAPP_NUMBERS, dict) else None
                        if cfg_fb:
                            import re as _re
                            treatment_from_wa = _re.sub(r"\D", "", cfg_fb.get("name", "")) or None
                except Exception as e_resolve:
                    print(f"[treatment_flow] WARNING - Could not resolve treatment phone_id for reply: {e_resolve}")
                    if not treatment_phone_id:
                        # as a last resort, pick first allowed treatment id
                        try:
                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                            treatment_phone_id = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                            from marketing.whatsapp_numbers import WHATSAPP_NUMBERS
                            cfg_fb2 = WHATSAPP_NUMBERS.get(str(treatment_phone_id)) if isinstance(WHATSAPP_NUMBERS, dict) else None
                            if cfg_fb2:
                                import re as _re
                                treatment_from_wa = _re.sub(r"\D", "", cfg_fb2.get("name", "")) or None
                        except Exception:
                            treatment_phone_id = None
                            treatment_from_wa = None

                if not treatment_phone_id:
                    print("[treatment_flow] WARNING - Skipping auto-reply: no treatment phone_id resolved (avoid using lead number)")
                    return {"status": "skipped_no_treatment_phone"}

                # Normalize from_wa_id to include country code (91) if needed
                def _normalize_from(sender: str | None) -> str | None:
                    if not sender:
                        return None
                    import re as _re
                    digits = _re.sub(r"\D", "", sender)
                    if len(digits) == 10:
                        return "91" + digits
                    return digits or sender

                treatment_from_wa = _normalize_from(treatment_from_wa)
                if not treatment_from_wa:
                    print("[treatment_flow] WARNING - Skipping auto-reply: no from_wa resolved for treatment number")
                    return {"status": "skipped_no_from_wa"}

                # Debounce quick replies to avoid duplicates (use appointment_state with short TTL)
                try:
                    from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                    from datetime import datetime, timedelta
                    st_qr = _appt_state.get(wa_id) or {}
                    last_qr_ts = st_qr.get("quick_reply_ts")
                    if last_qr_ts:
                        ts_obj = datetime.fromisoformat(last_qr_ts) if isinstance(last_qr_ts, str) else None
                        if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=8):
                            return {"status": "skipped_quick_reply_debounced"}
                except Exception:
                    pass

                # CRITICAL: Use original wa_id format - WhatsApp API expects the exact format customer used
                # Only normalize if wa_id is clearly incomplete (less than 10 digits)
                def _ensure_valid_wa_id(dest: str) -> str:
                    try:
                        import re as _re
                        digits = _re.sub(r"\D", "", dest or "")
                        # If it's a 10-digit number without country code, add 91
                        if len(digits) == 10:
                            return f"91{digits}"
                        # Otherwise use original format (WhatsApp API handles various formats)
                        return dest
                    except Exception:
                        return dest

                # Use original wa_id format for API call (WhatsApp expects exact format)
                target_wa_id = _ensure_valid_wa_id(wa_id)

                # CRITICAL: Ensure incoming_phone_id is set in appointment_state BEFORE sending
                # Set for both original and normalized formats to ensure _resolve_credentials works
                try:
                    from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                    # Set for original wa_id
                    st_for_send_orig = _appt_state.get(wa_id) or {}
                    # Set for target wa_id (in case it's different)
                    st_for_send_target = _appt_state.get(target_wa_id) or {}
                    if treatment_phone_id:
                        st_for_send_orig["incoming_phone_id"] = str(treatment_phone_id)
                        st_for_send_orig["treatment_flow_phone_id"] = str(treatment_phone_id)
                        st_for_send_target["incoming_phone_id"] = str(treatment_phone_id)
                        st_for_send_target["treatment_flow_phone_id"] = str(treatment_phone_id)
                        _appt_state[wa_id] = st_for_send_orig
                        if target_wa_id != wa_id:
                            _appt_state[target_wa_id] = st_for_send_target
                        print(f"[treatment_flow] DEBUG - Set incoming_phone_id={treatment_phone_id} for wa_id={wa_id} (target={target_wa_id}) before sending quick reply")
                except Exception as e_set:
                    print(f"[treatment_flow] WARNING - Could not set incoming_phone_id before sending: {e_set}")

                # Doctor/location/medicine deflection reply
                if any(k in normalized_body for k in doctor_location_keywords):
                    # Debounce to prevent duplicate sends
                    try:
                        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                        from datetime import datetime, timedelta
                        st_qr = _appt_state.get(wa_id) or {}
                        last_qr_ts = st_qr.get("quick_reply_ts")
                        if last_qr_ts:
                            ts_obj = datetime.fromisoformat(last_qr_ts) if isinstance(last_qr_ts, str) else None
                            if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=8):
                                return {"status": "skipped_deflection_debounced"}
                    except Exception:
                        pass
                    try:
                        deflect_msg = (
                            "Apologies! I’m a virtual assistant with limited responses. "
                            "Please select one of the options so I can assist you better."
                        )
                        await send_message_to_waid(
                            target_wa_id,
                            deflect_msg,
                            db,
                            phone_id_hint=treatment_phone_id,
                            from_wa_id=treatment_from_wa,
                            schedule_followup=False  # Do not schedule follow-ups for deflection
                        )
                        print(f"[treatment_flow] DEBUG - Sent deflection reply (doctor/location/medicine) to wa_id={target_wa_id}")
                    except Exception as e_send:
                        print(f"[treatment_flow] ERROR - Failed to send deflection reply: {e_send}")
                        import traceback
                        traceback.print_exc()
                        raise
                    try:
                        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                        from datetime import datetime
                        st_qr = _appt_state.get(wa_id) or {}
                        st_qr["quick_reply_ts"] = datetime.utcnow().isoformat()
                        _appt_state[wa_id] = st_qr
                    except Exception:
                        pass
                    return {"status": "handled_deflection"}

                # Treatment pricing reply (personalized cost explanation)
                if any(k in normalized_body for k in treatment_price_keywords):
                    msg_text = (
                        "All our treatments are personalized based on the severity of your concern and its root cause. "
                        "We don’t believe in “one-size-fits-all” solutions. We recommend booking an appointment for an "
                        "initial consultation with our dermatologist to get the exact cost for your treatment. "
                        "Please share your availability to book your appointment."
                    )
                    try:
                        print(f"[treatment_flow] DEBUG - Sending treatment price reply:")
                        print(f"  - Original wa_id: {wa_id}")
                        print(f"  - Target wa_id: {target_wa_id}")
                        print(f"  - Treatment phone_id: {treatment_phone_id}")
                        print(f"  - Treatment from_wa: {treatment_from_wa}")
                        # Send interactive button with the pricing message
                        cfg_btn = get_number_config(str(treatment_phone_id)) if treatment_phone_id else None
                        token_btn = (cfg_btn or {}).get("token")
                        if token_btn:
                            headers_btn = {
                                "Authorization": f"Bearer {token_btn}",
                                "Content-Type": "application/json",
                            }
                            payload_btn = {
                                "messaging_product": "whatsapp",
                                "to": target_wa_id,
                                "type": "interactive",
                                "interactive": {
                                    "type": "button",
                                    "body": {"text": msg_text},
                                    "action": {
                                        "buttons": [
                                            {
                                                "type": "reply",
                                                "reply": {"id": "confirm_appointment", "title": "Confirm Appointment"},
                                            }
                                        ]
                                    },
                                },
                            }
                            resp_btn = requests.post(get_messages_url(treatment_phone_id), headers=headers_btn, json=payload_btn)
                            print(f"[treatment_flow] DEBUG - Sent treatment price button via phone_id={treatment_phone_id}, status={resp_btn.status_code}")
                            if resp_btn.status_code == 200:
                                try:
                                    response_data_btn = resp_btn.json()
                                    msg_id_btn = response_data_btn.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                                    from services.customer_service import get_or_create_customer
                                    from schemas.customer_schema import CustomerCreate
                                    from services.message_service import create_message
                                    from schemas.message_schema import MessageCreate

                                    customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                                    message_rec = MessageCreate(
                                        message_id=msg_id_btn,
                                        from_wa_id=to_wa_id,
                                        to_wa_id=wa_id,
                                        type="interactive",
                                        body="Confirm Appointment (treatment price)",
                                        timestamp=datetime.now(),
                                        customer_id=customer.id,
                                    )
                                    create_message(db, message_rec)
                                    print(f"[treatment_flow] DEBUG - Saved treatment price interactive message: {msg_id_btn}")
                                except Exception as e_db:
                                    print(f"[treatment_flow] WARNING - Could not save treatment price interactive message: {e_db}")
                        else:
                            print(f"[treatment_flow] WARNING - Could not send treatment price button: no token for phone_id={treatment_phone_id}")
                    except Exception as e_send:
                        print(f"[treatment_flow] ERROR - Failed to send treatment price reply: {e_send}")
                        import traceback
                        traceback.print_exc()
                        raise
                    try:
                        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                        from datetime import datetime
                        st_qr = _appt_state.get(wa_id) or {}
                        st_qr["quick_reply_ts"] = datetime.utcnow().isoformat()
                        _appt_state[wa_id] = st_qr
                    except Exception:
                        pass
                    # Clear any completed flags and set state so the flow can restart on button click
                    try:
                        from controllers.web_socket import appointment_state as _appt_state_restart  # type: ignore
                        st_restart = _appt_state_restart.get(wa_id) or {}
                        # clear flow markers so Book Appointment goes through the fresh path
                        st_restart.pop("flow_completed", None)
                        st_restart.pop("treatment_expect_interactive", None)
                        st_restart.pop("treatment_welcome_sent", None)
                        st_restart.pop("treatment_welcome_sending_ts", None)
                        # keep phone mapping so credentials resolve correctly
                        st_restart["incoming_phone_id"] = str(treatment_phone_id)
                        st_restart["treatment_flow_phone_id"] = str(treatment_phone_id)
                        # mark as not in active treatment flow to force restart
                        st_restart.pop("flow_context", None)
                        st_restart.pop("from_treatment_flow", None)
                        _appt_state_restart[wa_id] = st_restart
                        print(f"[treatment_flow] DEBUG - Prepared state for flow restart after Book Appointment button: wa_id={wa_id}")
                    except Exception:
                        pass

                    # Explicitly clear any pending follow-up timers without scheduling new ones
                    try:
                        from services.followup_service import mark_customer_replied as _mark_replied
                        from services.customer_service import get_customer_record_by_wa_id as _get_cust
                        _cust = _get_cust(db, wa_id)
                        if _cust:
                            _mark_replied(db, customer_id=_cust.id, reset_followup_timer=False)
                            print(f"[treatment_flow] DEBUG - Cleared follow-up timer after treatment price auto-reply: wa_id={wa_id}")
                    except Exception:
                        pass
                    return {"status": "handled_treatment_price"}

                # Consultation fee reply (default consultation wording)
                if any(k in normalized_body for k in consult_keywords):
                    msg = (
                        "Our consultation fee is INR 900 only. At Oliva, we follow the V-Discover approach — a unique "
                        "5-step consultation process to thoroughly analyze your skin, hair, and body. As part of your "
                        "consultation, you will also receive:\n"
                        "· Full Body Composition Analysis (BCA)\n"
                        "· Nutritionist consultation\n"
                        "· Dermatologist consultation\n\n"
                        "This ensures a comprehensive understanding of your needs and helps us design a treatment plan that's just right for you. "
                        "Please share your availability to book your appointment!"
                    )
                    try:
                        print(f"[treatment_flow] DEBUG - Sending consultation fee reply:")
                        print(f"  - Original wa_id: {wa_id}")
                        print(f"  - Target wa_id: {target_wa_id}")
                        print(f"  - Treatment phone_id: {treatment_phone_id}")
                        print(f"  - Treatment from_wa: {treatment_from_wa}")
                        await send_message_to_waid(
                            target_wa_id,
                            msg,
                            db,
                            phone_id_hint=treatment_phone_id,
                            from_wa_id=treatment_from_wa,
                            schedule_followup=False  # No follow-up for free text consultation fee queries
                        )
                        print(f"[treatment_flow] DEBUG - Successfully sent consultation fee reply to wa_id={target_wa_id}")
                    except Exception as e_send:
                        print(f"[treatment_flow] ERROR - Failed to send consultation fee reply: {e_send}")
                        import traceback
                        traceback.print_exc()
                        raise
                    try:
                        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                        from datetime import datetime
                        st_qr = _appt_state.get(wa_id) or {}
                        st_qr["quick_reply_ts"] = datetime.utcnow().isoformat()
                        _appt_state[wa_id] = st_qr
                    except Exception:
                        pass
                    # Explicitly clear any pending follow-up timers without scheduling new ones
                    try:
                        from services.followup_service import mark_customer_replied as _mark_replied
                        from services.customer_service import get_customer_record_by_wa_id as _get_cust
                        _cust = _get_cust(db, wa_id)
                        if _cust:
                            _mark_replied(db, customer_id=_cust.id, reset_followup_timer=False)
                            print(f"[treatment_flow] DEBUG - Cleared follow-up timer after consultation fee auto-reply: wa_id={wa_id}")
                    except Exception:
                        pass
                    return {"status": "handled_consultation_fee"}

                if any(k in normalized_body for k in job_keywords):
                    msg = "For job-related enquiries, please contact our HR team at: hr@olivaclinic.com"
                    try:
                        print(f"[treatment_flow] DEBUG - Sending job query reply:")
                        print(f"  - Original wa_id: {wa_id}")
                        print(f"  - Target wa_id: {target_wa_id}")
                        print(f"  - Treatment phone_id: {treatment_phone_id}")
                        print(f"  - Treatment from_wa: {treatment_from_wa}")
                        await send_message_to_waid(
                            target_wa_id,
                            msg,
                            db,
                            phone_id_hint=treatment_phone_id,
                            from_wa_id=treatment_from_wa,
                            schedule_followup=False  # No follow-up for free text job queries
                        )
                        print(f"[treatment_flow] DEBUG - Successfully sent job query reply to wa_id={target_wa_id}")
                    except Exception as e_send:
                        print(f"[treatment_flow] ERROR - Failed to send job query reply: {e_send}")
                        import traceback
                        traceback.print_exc()
                        raise
                    try:
                        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                        from datetime import datetime
                        st_qr = _appt_state.get(wa_id) or {}
                        st_qr["quick_reply_ts"] = datetime.utcnow().isoformat()
                        _appt_state[wa_id] = st_qr
                    except Exception:
                        pass
                    # Explicitly clear any pending follow-up timers without scheduling new ones
                    try:
                        from services.followup_service import mark_customer_replied as _mark_replied
                        from services.customer_service import get_customer_record_by_wa_id as _get_cust
                        _cust = _get_cust(db, wa_id)
                        if _cust:
                            _mark_replied(db, customer_id=_cust.id, reset_followup_timer=False)
                            print(f"[treatment_flow] DEBUG - Cleared follow-up timer after job query auto-reply: wa_id={wa_id}")
                    except Exception:
                        pass
                    return {"status": "handled_job_query"}
            except Exception as e_quick:
                print(f"[treatment_flow] WARNING - Quick reply failed: {e_quick}")

        # Prefill detected if:
        # 1. There's a message body, AND
        # 2. Customer is messaging a treatment flow number, AND
        # 3. Customer has NOT already received welcome (not in active flow)
        prefill_detected = bool(normalized_body) and is_current_number_treatment and not in_active_treatment_flow
        matched_pattern = "any_text_start" if prefill_detected else None

        _safe_debug(
            "prefill_detection",
            wa_id=wa_id,
            message_id=message_id,
            normalized_body=normalized_body,
            prefill_detected=prefill_detected,
            matched_pattern=matched_pattern,
            in_active_treatment_flow=in_active_treatment_flow,
        )

        if prefill_detected:
            # Step 1: Send welcome message when customer sends any message
            try:
                # Ensure send_message_to_waid is available (imported at module level)
                from utils.whatsapp import send_message_to_waid as _send_msg
                
                # Resolve credentials for sending welcome message
                def _resolve_credentials_for_welcome() -> tuple[str | None, str | None]:
                    try:
                        phone_id_meta = ((value or {}).get("metadata", {}) or {}).get("phone_number_id")
                        display_phone = ((value or {}).get("metadata", {}) or {}).get("display_phone_number")
                        
                        # First try: Check if phone_id_meta is in allowed list
                        if phone_id_meta:
                            cfg = get_number_config(str(phone_id_meta))
                            if cfg and cfg.get("token"):
                                return cfg.get("token"), str(phone_id_meta)
                        
                        # Second try: Match by display_phone_number (for local testing)
                        if display_phone:
                            import re as _re
                            disp_digits = _re.sub(r"\D", "", str(display_phone))
                            disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS, WHATSAPP_NUMBERS
                            for pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                cfg = WHATSAPP_NUMBERS.get(pid) if isinstance(WHATSAPP_NUMBERS, dict) else None
                                if cfg:
                                    name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                                    name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                                    if name_last10 and disp_last10 and name_last10 == disp_last10:
                                        if cfg.get("token"):
                                            return cfg.get("token"), str(pid)
                    except Exception:
                        pass
                    try:
                        from controllers.web_socket import appointment_state  # type: ignore
                        st = appointment_state.get(wa_id) or {}
                        incoming_phone_id = st.get("incoming_phone_id")
                        if incoming_phone_id:
                            cfg = get_number_config(str(incoming_phone_id))
                            if cfg and cfg.get("token"):
                                return cfg.get("token"), str(incoming_phone_id)
                    except Exception:
                        pass
                    try:
                        from services.whatsapp_service import get_latest_token
                        token_entry = get_latest_token(db)
                        if token_entry and token_entry.token:
                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                            phone_id = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0] if TREATMENT_FLOW_ALLOWED_PHONE_IDS else None
                            if phone_id:
                                cfg = get_number_config(str(phone_id))
                                if cfg and cfg.get("token"):
                                    return cfg.get("token"), str(phone_id)
                    except Exception:
                        pass
                    return None, None

                access_token_welcome, phone_id_welcome = _resolve_credentials_for_welcome()
                print(f"[treatment_flow] DEBUG - Credentials resolved: access_token={bool(access_token_welcome)}, phone_id={phone_id_welcome}")
                if access_token_welcome and phone_id_welcome:
                    # Send welcome message
                    welcome_message = "Hi! Thanks for reaching out to Oliva Clinics. I'm your virtual assistant here to help you instantly."
                    print(f"[treatment_flow] DEBUG - Sending welcome message to wa_id={wa_id} from phone_id={phone_id_welcome}")
                    # CRITICAL: schedule_followup=False - Flow not started yet (will start after city selection)
                    await _send_msg(wa_id, welcome_message, db, phone_id_hint=str(phone_id_welcome), schedule_followup=False)
                    
                    # Mark flow context and store phone_id
                    try:
                        from controllers.web_socket import appointment_state  # type: ignore
                        st = appointment_state.get(wa_id) or {}
                        st["flow_context"] = "treatment"
                        st["from_treatment_flow"] = True
                        st["treatment_flow_phone_id"] = str(phone_id_welcome)
                        st["incoming_phone_id"] = str(phone_id_welcome)
                        st["treatment_welcome_sent"] = True  # Mark treatment welcome as sent to prevent duplicates
                        appointment_state[wa_id] = st
                        print(f"[treatment_flow] DEBUG - Marked treatment_welcome_sent=True for wa_id={wa_id}")
                    except Exception:
                        pass
                    
                    # Step 2: Send city selection after welcome message
                    try:
                        from marketing.city_selection import send_city_selection
                        await send_city_selection(db, wa_id=wa_id, phone_id_hint=str(phone_id_welcome))
                    except Exception as e:
                        print(f"[treatment_flow] WARNING - Could not send city selection: {e}")
                    
                    handled_text = True
                    return {"status": "welcome_sent", "message_id": message_id}
            except Exception as e:
                print(f"[treatment_flow] ERROR - Could not send welcome message: {e}")
                import traceback
                traceback.print_exc()
                # Continue to old flow logic if welcome fails

            # Clear stale state to allow flow restart when customer sends a starting point message
            try:
                from controllers.state.memory import clear_flow_state_for_restart
                clear_flow_state_for_restart(wa_id)
                print(f"[treatment_flow] DEBUG - Cleared stale state for new flow start (prefill detected): wa_id={wa_id}")
            except Exception as e:
                print(f"[treatment_flow] WARNING - Could not clear stale state: {e}")
            # Restrict treatment flow to only allowed phone numbers
            # Note: This check is now handled earlier in the flow, but keeping for backward compatibility
            # The welcome message is already sent above if prefill_detected, so we can skip this check
            # However, we still need to check if we're in an active flow to avoid duplicate sends
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            phone_id_meta = ((value or {}).get("metadata", {}) or {}).get("phone_number_id")
            
            # Check if the incoming phone number is allowed for treatment flow
            is_allowed = False
            if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                is_allowed = True
            else:
                # Also check by display phone number as fallback - compare last 10 digits
                try:
                    display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                    import re as _re
                    disp_digits = _re.sub(r"\D", "", display_num or "")
                    # Get last 10 digits of display number (phone number without country code)
                    disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                    
                    for pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                        cfg = WHATSAPP_NUMBERS.get(pid)
                        if cfg:
                            name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                            # Get last 10 digits of stored phone number
                            name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                            # Match if last 10 digits are the same
                            if name_last10 and disp_last10 and name_last10 == disp_last10:
                                is_allowed = True
                                break
                except Exception:
                    pass
            
            # Skip this check if welcome was already sent (handled above)
            # Only proceed if this is an allowed phone number AND welcome wasn't already sent
            if not is_allowed and not handled_text:
                display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                _safe_debug(
                    "phone_not_allowed_for_treatment",
                    wa_id=wa_id,
                    message_id=message_id,
                    phone_id_meta=phone_id_meta,
                    display_number=display_num,
                )
                return {"status": "skipped", "message_id": message_id, "reason": "phone_number_not_allowed"}
            
            
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                from datetime import datetime, timedelta
                st_lock = appointment_state.get(wa_id) or {}
                # First check if treatment welcome was already sent - if so, skip sending again
                if bool(st_lock.get("treatment_welcome_sent")):
                    # Check timestamp to see if it was sent very recently (within 10 seconds)
                    ts_str = st_lock.get("treatment_welcome_sending_ts")
                    ts_obj = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else None
                    if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=10):
                        print(f"[treatment_flow] DEBUG - Skipping duplicate treatment welcome: already sent by another handler (wa_id={wa_id})")
                        return {"status": "skipped", "message_id": message_id, "reason": "treatment_welcome_already_sent"}
                # Check if treatment welcome is currently being sent (within 10 seconds) to prevent race conditions
                ts_str = st_lock.get("treatment_welcome_sending_ts")
                ts_obj = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else None
                if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=10):
                    return {"status": "skipped", "message_id": message_id, "reason": "treatment_welcome_in_progress"}
                # Set sending timestamp to prevent concurrent sends
                st_lock["treatment_welcome_sending_ts"] = datetime.utcnow().isoformat()
                appointment_state[wa_id] = st_lock
            except Exception:
                pass

            # Determine and store the phone_id that triggered this flow
            flow_phone_id = None
            if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                flow_phone_id = str(phone_id_meta)
            else:
                # Find phone_id by display number match - compare last 10 digits
                try:
                    display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                    import re as _re
                    disp_digits = _re.sub(r"\D", "", display_num or "")
                    # Get last 10 digits of display number
                    disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                    
                    for pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                        cfg = WHATSAPP_NUMBERS.get(pid)
                        if cfg:
                            name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                            # Get last 10 digits of stored phone number
                            name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                            # Match if last 10 digits are the same
                            if name_last10 and disp_last10 and name_last10 == disp_last10:
                                flow_phone_id = str(pid)
                                break
                except Exception:
                    pass
            
            try:
                # Extract location and city from the incoming prefill text if present
                # Expected: "hi oliva i want to know more about services in <location>, <city> clinic"
                extracted_location = None
                extracted_city = None
                try:
                    _m = re.search(r"services\s+in\s+([a-z\s]+),\s*([a-z\s]+)\s+clinic$", normalized_body, flags=re.IGNORECASE)
                    if _m:
                        extracted_location = (_m.group(1) or "").strip().title()
                        extracted_city = (_m.group(2) or "").strip().title()
                except Exception:
                    pass

                # Persist into state for later lead creation (including the phone_id that triggered this flow)
                try:
                    from controllers.web_socket import appointment_state, lead_appointment_state  # type: ignore
                    st_prefill = appointment_state.get(wa_id) or {}
                    if extracted_city:
                        st_prefill["selected_city"] = extracted_city
                    if extracted_location:
                        st_prefill["selected_location"] = extracted_location
                    if flow_phone_id:
                        st_prefill["treatment_flow_phone_id"] = flow_phone_id  # Store the phone_id for this flow
                    appointment_state[wa_id] = st_prefill
                    # Mirror minimal info into lead_appointment_state
                    try:
                        lst_prefill = lead_appointment_state.get(wa_id) or {}
                        if extracted_city:
                            lst_prefill["selected_city"] = extracted_city
                        if extracted_location:
                            lst_prefill["selected_location"] = extracted_location
                        lead_appointment_state[wa_id] = lst_prefill
                    except Exception:
                        pass
                except Exception:
                    pass

                # Resolve credentials (multi-number aware) - use the phone_id that triggered this flow
                def _resolve_credentials_for_value() -> tuple[str | None, str | None]:
                    # First priority: use the phone_id that triggered this flow (stored in flow_phone_id)
                    if flow_phone_id:
                        cfg = get_number_config(flow_phone_id)
                        if cfg and cfg.get("token"):
                            return cfg.get("token"), flow_phone_id
                    
                    try:
                        phone_id_meta = ((value or {}).get("metadata", {}) or {}).get("phone_number_id")
                        if phone_id_meta:
                            cfg = get_number_config(str(phone_id_meta))
                            if cfg and cfg.get("token"):
                                return cfg.get("token"), str(phone_id_meta)
                        # Fallback: match by display phone number
                        try:
                            display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                            import re as _re
                            disp_digits = _re.sub(r"\D", "", display_num or "")
                            for pid, cfg in (WHATSAPP_NUMBERS or {}).items():
                                name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                                if name_digits and name_digits.endswith(disp_digits):
                                    tok = cfg.get("token")
                                    if tok:
                                        return tok, str(pid)
                        except Exception:
                            pass
                        
                    except Exception:
                        pass
                    # Final fallback: DB token + use flow_phone_id if available, else first allowed number
                    t = get_latest_token(db)
                    if t and getattr(t, "token", None):
                        # Use flow_phone_id if available, otherwise use first allowed number
                        fallback_phone_id = flow_phone_id if flow_phone_id else list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                        return t.token, fallback_phone_id
                    return None, None

                access_token_prefill, phone_id_prefill = _resolve_credentials_for_value()
                if access_token_prefill:
                    # Treatment welcome message (text) sent instead of mr_welcome template
                    # Mark context and set treatment flag
                    try:
                        from controllers.web_socket import appointment_state  # type: ignore
                        st = appointment_state.get(wa_id) or {}
                        st["flow_context"] = "treatment"
                        st["from_treatment_flow"] = True
                        if phone_id_prefill:
                            st["treatment_flow_phone_id"] = phone_id_prefill
                        appointment_state[wa_id] = st
                    except Exception:
                        pass
                    handled_text = True
                    return {"status": "skipped", "message_id": message_id}
                else:
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template_error",
                            "message": "treatment welcome not sent: no WhatsApp token",
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
            except Exception:
                # Continue to other logic below even if welcome attempt fails
                pass

        # Name/Contact verification removed as per new requirements.

    return {"status": "skipped" if not handled_text else "handled", "message_id": message_id}


async def run_treatment_buttons_flow(
    db: Session,
    *,
    wa_id: str,
    to_wa_id: str,
    message_id: str,
    btn_id: str | None = None,
    btn_text: str | None = None,
    btn_payload: str | None = None,
) -> Dict[str, Any]:
    """Handle Skin/Hair/Body treatment topic buttons and list selections."""
    # Clear any pending interactive expectation now that we received a structured reply
    try:
        from controllers.web_socket import appointment_state as _appt_state  # type: ignore
        st_clear = _appt_state.get(wa_id) or {}
        st_clear.pop("treatment_expect_interactive", None)
        _appt_state[wa_id] = st_clear
    except Exception:
        pass
    # Strongest possible check: don't process any treatment action if this is a catalog/buy flow.
    catalog_triggers = {"buy_products", "buy product", "buy products", "show catalogue", "catalogue", "catalog", "browse products"}
    for val in (btn_id, btn_text, btn_payload):
        if val and any(kw in val.lower() for kw in catalog_triggers):
            print(f"[treatment_flow] DEBUG - Skipping treatment logic for catalog trigger: {val}")
            return {"status": "skipped"}

    # Topic buttons: Skin / Hair / Body
    topic = (btn_id or btn_text or "").strip().lower()
    print(f"[treatment_flow] DEBUG - run_treatment_buttons_flow called: btn_id={btn_id}, btn_text={btn_text}, topic={topic}")
    if topic in {"skin", "hair", "body"}:
        print(f"[treatment_flow] DEBUG - Topic '{topic}' matched, processing...")
        # NOTE: Do NOT set any fallback concern here.
        # We should only persist the precise list selection the user makes next.
        try:
            # Resolve credentials for template sends during topic handling
            def _resolve_creds_topic() -> tuple[str | None, str | None]:
                # 1) First priority: use the phone_id stored in state from when flow started
                try:
                    from controllers.web_socket import appointment_state  # type: ignore
                    st = appointment_state.get(wa_id) or {}
                    stored_phone_id = st.get("treatment_flow_phone_id")
                    if stored_phone_id:
                        cfg = WHATSAPP_NUMBERS.get(str(stored_phone_id)) if isinstance(WHATSAPP_NUMBERS, dict) else None
                        if cfg and cfg.get("token"):
                            return cfg.get("token"), str(stored_phone_id)
                except Exception:
                    pass
                # 2) Try to infer from display number we are broadcasting as (to_wa_id)
                try:
                    import re as _re
                    disp_digits = _re.sub(r"\D", "", to_wa_id or "")
                    for pid, cfg in (WHATSAPP_NUMBERS or {}).items():
                        name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                        if name_digits and name_digits.endswith(disp_digits) and cfg.get("token"):
                            return cfg.get("token"), str(pid)
                except Exception:
                    pass
                # 3) Fallback: DB token + use stored phone_id or first allowed number
                t = get_latest_token(db)
                if t and getattr(t, "token", None):
                    try:
                        from controllers.web_socket import appointment_state  # type: ignore
                        st = appointment_state.get(wa_id) or {}
                        stored_phone_id = st.get("treatment_flow_phone_id")
                        if stored_phone_id:
                            fallback_pid = stored_phone_id
                        else:
                            # Use first allowed number as fallback
                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                            fallback_pid = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                    except Exception:
                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                        fallback_pid = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                    return t.token, str(fallback_pid)
                return None, None

            access_token2, phone_id2 = _resolve_creds_topic()
            print(f"[treatment_flow] DEBUG - Topic '{topic}' selected. Credentials resolved: access_token={bool(access_token2)}, phone_id={phone_id2}")
            if access_token2:
                from controllers.auto_welcome_controller import _send_template
                lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                if topic == "skin":
                    print(f"[treatment_flow] DEBUG - Sending skin_treat_flow template to wa_id={wa_id}")
                    resp_skin = _send_template(wa_id=wa_id, template_name="skin_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    print(f"[treatment_flow] DEBUG - skin_treat_flow response status: {resp_skin.status_code}")
                    # Save template message to database
                    if resp_skin.status_code == 200:
                        try:
                            response_data = resp_skin.json()
                            template_message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                            
                            from services.customer_service import get_or_create_customer
                            from schemas.customer_schema import CustomerCreate
                            from services.message_service import create_message
                            from schemas.message_schema import MessageCreate
                            
                            customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                            
                            template_message = MessageCreate(
                                message_id=template_message_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body="skin_treat_flow",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                            )
                            create_message(db, template_message)
                            print(f"[treatment_flow] DEBUG - skin_treat_flow template saved to database: {template_message_id}")
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Failed to save skin_treat_flow template to database: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    try:
                        response_data_skin = resp_skin.json() if resp_skin.status_code == 200 else {}
                        template_message_id_skin = response_data_skin.get("messages", [{}])[0].get("id", "") if resp_skin.status_code == 200 else ""
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template",
                            "message": "skin_treat_flow",
                            "body": "skin_treat_flow",
                            "timestamp": datetime.now().isoformat(),
                            "message_id": template_message_id_skin,
                            **({"status_code": resp_skin.status_code} if resp_skin.status_code != 200 else {}),
                        })
                    except Exception:
                        pass
                    if resp_skin.status_code == 200:
                        try:
                            from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                            st_expect = _appt_state.get(wa_id) or {}
                            st_expect["treatment_expect_interactive"] = "skin_treat_flow"
                            _appt_state[wa_id] = st_expect
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
                                            {"id": "dandruff", "title": "Dandruff & Scalp Care"},
                                            {"id": "other_skin", "title": "Other Skin Concerns"},
                                        ],
                                    }
                                ],
                            },
                        },
                    }
                    resp_list = requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                    if resp_list.status_code == 200:
                        try:
                            # Save outbound message to database
                            response_data = resp_list.json()
                            message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                            
                            from services.message_service import create_message
                            from schemas.message_schema import MessageCreate
                            
                            outbound_message = MessageCreate(
                                message_id=message_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="interactive",
                                body=f"Choose your {topic} treatment:",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                            )
                            create_message(db, outbound_message)
                            print(f"[treatment_flow] DEBUG - Outbound treatment list saved to database: {message_id}")
                            
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "interactive",
                                "message": f"Choose your {topic} treatment:",
                                "timestamp": datetime.now().isoformat(),
                                "meta": {"kind": "list", "section": f"{topic.title()} Treatments"}
                            })
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
                        # Expect a list reply next
                        try:
                            from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                            st_expect = _appt_state.get(wa_id) or {}
                            st_expect["treatment_expect_interactive"] = "concern_list"
                            _appt_state[wa_id] = st_expect
                        except Exception:
                            pass
                    return {"status": "list_sent", "message_id": message_id}

                if topic == "hair":
                    resp_hair = _send_template(wa_id=wa_id, template_name="hair_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    # Save template message to database
                    if resp_hair.status_code == 200:
                        try:
                            response_data = resp_hair.json()
                            template_message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                            
                            from services.customer_service import get_or_create_customer
                            from schemas.customer_schema import CustomerCreate
                            from services.message_service import create_message
                            from schemas.message_schema import MessageCreate
                            
                            customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                            
                            template_message = MessageCreate(
                                message_id=template_message_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body="hair_treat_flow",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                            )
                            create_message(db, template_message)
                            print(f"[treatment_flow] DEBUG - hair_treat_flow template saved to database: {template_message_id}")
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Failed to save hair_treat_flow template to database: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    try:
                        response_data_hair = resp_hair.json() if resp_hair.status_code == 200 else {}
                        template_message_id_hair = response_data_hair.get("messages", [{}])[0].get("id", "") if resp_hair.status_code == 200 else ""
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template",
                            "message": "hair_treat_flow",
                            "body": "hair_treat_flow",
                            "timestamp": datetime.now().isoformat(),
                            "message_id": template_message_id_hair,
                            **({"status_code": resp_hair.status_code} if resp_hair.status_code != 200 else {}),
                        })
                    except Exception:
                        pass
                    if resp_hair.status_code == 200:
                        try:
                            from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                            st_expect = _appt_state.get(wa_id) or {}
                            st_expect["treatment_expect_interactive"] = "hair_treat_flow"
                            _appt_state[wa_id] = st_expect
                        except Exception:
                            pass
                    return {"status": "hair_template_sent", "message_id": message_id}

                if topic == "body":
                    resp_body = _send_template(wa_id=wa_id, template_name="body_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    # Save template message to database
                    if resp_body.status_code == 200:
                        try:
                            response_data = resp_body.json()
                            template_message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                            
                            from services.customer_service import get_or_create_customer
                            from schemas.customer_schema import CustomerCreate
                            from services.message_service import create_message
                            from schemas.message_schema import MessageCreate
                            
                            customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                            
                            template_message = MessageCreate(
                                message_id=template_message_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body="body_treat_flow",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                            )
                            create_message(db, template_message)
                            print(f"[treatment_flow] DEBUG - body_treat_flow template saved to database: {template_message_id}")
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Failed to save body_treat_flow template to database: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    try:
                        response_data_body = resp_body.json() if resp_body.status_code == 200 else {}
                        template_message_id_body = response_data_body.get("messages", [{}])[0].get("id", "") if resp_body.status_code == 200 else ""
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template",
                            "message": "body_treat_flow",
                            "body": "body_treat_flow",
                            "timestamp": datetime.now().isoformat(),
                            "message_id": template_message_id_body,
                            **({"status_code": resp_body.status_code} if resp_body.status_code != 200 else {}),
                        })
                    except Exception:
                        pass
                    if resp_body.status_code == 200:
                        try:
                            from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                            st_expect = _appt_state.get(wa_id) or {}
                            st_expect["treatment_expect_interactive"] = "body_treat_flow"
                            _appt_state[wa_id] = st_expect
                        except Exception:
                            pass
                    return {"status": "body_template_sent", "message_id": message_id}
            else:
                print(f"[treatment_flow] WARNING - Could not resolve credentials for topic '{topic}'. access_token2={bool(access_token2)}, phone_id2={phone_id2}")
        except Exception as e:
            print(f"[treatment_flow] ERROR - Exception in topic handling for '{topic}': {e}")
            import traceback
            traceback.print_exc()
            pass

    # List selections arriving as plain buttons
    norm_btn = (btn_id or btn_text or btn_payload or "").strip().lower()
    # Canonicalize label/id to avoid hyphen/space/ampersand differences
    def _canon(txt: str) -> str:
        try:
            import re as _re
            return _re.sub(r"[^a-z0-9]+", " ", (txt or "").lower()).strip()
        except Exception:
            return (txt or "").lower().strip()

    canon_btn = _canon(norm_btn)

    skin_concerns = {
        "acne acne scars",
        "pigmentation",
        "uneven skin tone",
        "anti aging",
        "skin rejuvenation",
        "laser hair removal",
        "other skin concerns",
    }
    hair_concerns = {
        "hair loss hair fall",
        "hair transplant",
        "dandruff scalp care",
        "other hair concerns",
    }
    body_concerns = {
        "weight management",
        "body contouring",
        "weight loss",
        "other body concerns",
    }

    if canon_btn in skin_concerns or canon_btn in hair_concerns or canon_btn in body_concerns:
        # Persist the user's selected concern so lead creation can map it later
        try:
            # Map canonical keys to display labels used in DB mappings
            synonyms_to_canonical = {
                # Skin
                "acne acne scars": "Acne / Acne Scars",
                "pigmentation": "Pigmentation & Uneven Skin Tone",
                "uneven skin tone": "Pigmentation & Uneven Skin Tone",
                "anti aging": "Anti-Aging & Skin Rejuvenation",
                "skin rejuvenation": "Anti-Aging & Skin Rejuvenation",
                "laser hair removal": "Laser Hair Removal",
                "other skin concerns": "Other Skin Concerns",
                # Hair
                "hair loss hair fall": "Hair Loss / Hair Fall",
                "hair transplant": "Hair Transplant",
                "dandruff scalp care": "Dandruff & Scalp Care",
                "other hair concerns": "Other Hair Concerns",
                # Body
                "weight management": "Weight Management",
                "body contouring": "Body Contouring",
                "weight loss": "Weight Loss",
                "other body concerns": "Other Body Concerns",
            }

            selected_concern_label = synonyms_to_canonical.get(canon_btn, (btn_text or btn_payload or btn_id or "").strip())

            # Save to in-memory state used across flows
            from controllers.web_socket import appointment_state, lead_appointment_state  # type: ignore
            try:
                if wa_id not in appointment_state:
                    appointment_state[wa_id] = {}
                appointment_state[wa_id]["selected_concern"] = selected_concern_label
                # Clear error prompt timestamp when user selects a valid option
                appointment_state[wa_id].pop("error_prompt_sent_timestamp", None)
                print(f"[treatment_flow] DEBUG - Stored selected concern: {selected_concern_label} and cleared error prompt timestamp")
            except Exception:
                pass
            try:
                if wa_id not in lead_appointment_state:
                    lead_appointment_state[wa_id] = {}
                lead_appointment_state[wa_id]["selected_concern"] = selected_concern_label
            except Exception:
                pass
            
            # Step 5: Send final thank you message after specific concern is selected
            try:
                from utils.whatsapp import send_message_to_waid
                final_message = "Thank you for your interest in Oliva Clinic! One of our team members will get back to you shortly to assist you better."
                # Resolve phone_id for sending final message
                st_final = appointment_state.get(wa_id) or {}
                phone_id_final = st_final.get("treatment_flow_phone_id") or st_final.get("incoming_phone_id")
                # CRITICAL: schedule_followup=False - NO follow-up after final step
                await send_message_to_waid(wa_id, final_message, db, phone_id_hint=str(phone_id_final) if phone_id_final else None, schedule_followup=False)
                
                # CRITICAL: Clear treatment_expect_interactive and mark flow as completed
                # This prevents any further prompts from being sent
                try:
                    st_final.pop("treatment_expect_interactive", None)
                    st_final["flow_completed"] = True
                    st_final.pop("error_prompt_sent_timestamp", None)  # Clear error prompt timestamp
                    appointment_state[wa_id] = st_final
                    print(f"[treatment_flow] DEBUG - Flow completed: cleared treatment_expect_interactive for wa_id={wa_id}")
                except Exception as e:
                    print(f"[treatment_flow] WARNING - Could not clear treatment_expect_interactive: {e}")
                
                # CRITICAL: Create lead immediately after final step (no follow-up scheduled)
                try:
                    from services.customer_service import get_customer_record_by_wa_id
                    from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
                    
                    customer = get_customer_record_by_wa_id(db, wa_id)
                    if customer:
                        # Prepare appointment details for treatment flow
                        selected_city = st_final.get("selected_city", "")
                        appointment_details = {
                            "flow_type": "treatment_flow",
                            "selected_city": selected_city,
                            "selected_concern": selected_concern_label,
                            "dropoff_point": "flow_completed"
                        }
                        
                        print(f"\n{'='*80}")
                        print(f"📝 [LEAD CREATION] After Final Step (Flow Completed)")
                        print(f"   Customer: {wa_id}")
                        print(f"   Concern: {selected_concern_label}")
                        print(f"   City: {selected_city}")
                        print(f"   Action: Creating lead in Zoho...")
                        print(f"{'='*80}\n")
                        
                        res = await create_lead_for_appointment(
                            db=db,
                            wa_id=wa_id,
                            customer=customer,
                            appointment_details=appointment_details,
                            lead_status="CALL_INITIATED",
                            appointment_preference=f"Treatment flow completed - Concern: {selected_concern_label}"
                        )
                        
                        # Enhanced logging for lead creation result
                        if res and res.get("success") and not res.get("skipped"):
                            zoho_lead_id = res.get("lead_id") or res.get("zoho_lead_id") or res.get("id") or "N/A"
                            print(f"\n{'='*80}")
                            print(f"✅ [LEAD CREATED SUCCESSFULLY] After Final Step")
                            print(f"   Customer: {wa_id}")
                            print(f"   Zoho Lead ID: {zoho_lead_id}")
                            print(f"   Lead Source: Business Listing")
                            print(f"   Sub Source: WhatsApp Dial")
                            print(f"   Status: CALL_INITIATED")
                            print(f"{'='*80}\n")
                        elif res and res.get("skipped"):
                            skip_reason = res.get("reason") or "Unknown reason"
                            print(f"\n{'='*80}")
                            print(f"⏭️  [LEAD CREATION SKIPPED] After Final Step")
                            print(f"   Customer: {wa_id}")
                            print(f"   Reason: {skip_reason}")
                            print(f"{'='*80}\n")
                        else:
                            error_msg = res.get("error") if res else "Unknown error"
                            print(f"\n{'='*80}")
                            print(f"❌ [LEAD CREATION FAILED] After Final Step")
                            print(f"   Customer: {wa_id}")
                            print(f"   Error: {error_msg}")
                            print(f"{'='*80}\n")
                    else:
                        print(f"[treatment_flow] WARNING - Could not get customer record for lead creation: wa_id={wa_id}")
                except Exception as e:
                    print(f"[treatment_flow] ERROR - Could not create lead after final step: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Clear any pending follow-up timers (no follow-up after final step)
                try:
                    from services.followup_service import mark_customer_replied as _mark_replied
                    from services.customer_service import get_customer_record_by_wa_id as _get_cust
                    _cust = _get_cust(db, wa_id)
                    if _cust:
                        _mark_replied(db, customer_id=_cust.id, reset_followup_timer=False)
                        print(f"[treatment_flow] DEBUG - Cleared follow-up timer for completed flow: wa_id={wa_id}")
                except Exception:
                    pass
                
                return {"status": "concern_selected", "selected_concern": selected_concern_label, "message_id": message_id}
            except Exception as e:
                print(f"[treatment_flow] WARNING - Could not send final thank you message: {e}")
                import traceback
                traceback.print_exc()
        except Exception:
            pass
        try:
            # Resolve credentials to ensure booking_appoint goes from Treatment Flow number
            token_entry_book = get_latest_token(db)
            if token_entry_book and token_entry_book.token:
                # 1) First priority: use the phone_id stored in state from when flow started
                access_token_book = None
                phone_id_book = None
                try:
                    from controllers.web_socket import appointment_state  # type: ignore
                    st = appointment_state.get(wa_id) or {}
                    stored_phone_id = st.get("treatment_flow_phone_id")
                    if stored_phone_id:
                        from marketing.whatsapp_numbers import WHATSAPP_NUMBERS  # type: ignore
                        cfg_b = (WHATSAPP_NUMBERS or {}).get(str(stored_phone_id)) if isinstance(WHATSAPP_NUMBERS, dict) else None
                        if cfg_b and cfg_b.get("token"):
                            access_token_book = cfg_b.get("token")
                            phone_id_book = str(stored_phone_id)
                except Exception:
                    pass
                # 2) Infer from to_wa_id display number mapping
                if not access_token_book:
                    try:
                        import re as _re
                        from marketing.whatsapp_numbers import WHATSAPP_NUMBERS  # type: ignore
                        disp_digits_b = _re.sub(r"\D", "", to_wa_id or "")
                        for pid, cfg in (WHATSAPP_NUMBERS or {}).items():
                            name_digits_b = _re.sub(r"\D", "", (cfg.get("name") or ""))
                            if name_digits_b and name_digits_b.endswith(disp_digits_b) and cfg.get("token"):
                                access_token_book = cfg.get("token")
                                phone_id_book = str(pid)
                                break
                    except Exception:
                        pass
                # 3) Fallback: DB token + use stored phone_id or first allowed number
                if not access_token_book:
                    access_token_book = token_entry_book.token
                    try:
                        from controllers.web_socket import appointment_state  # type: ignore
                        st = appointment_state.get(wa_id) or {}
                        stored_phone_id = st.get("treatment_flow_phone_id")
                        if stored_phone_id:
                            phone_id_book = stored_phone_id
                        else:
                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                            phone_id_book = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                    except Exception:
                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                        phone_id_book = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]

                # booking_appoint template removed
                # Do NOT send thank-you here; send it only after the user clicks "Book an Appointment"
        except Exception:
            pass

        # Book Appointment / Request Call Back buttons removed
        except Exception:
            pass

    return {"status": "skipped"}


async def run_book_appointment_flow(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Trigger the appointment date list for a user.

    Delegates to the existing date list sender while avoiding circular imports.
    """

    try:
        # Local import to avoid circular dependency
        from controllers.components.interactive_type import send_week_list  # type: ignore
        await send_week_list(db, wa_id)
        return {"status": "week_list_sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def run_confirm_appointment_flow(
    db: Session,
    *,
    wa_id: str,
    date_iso: str,
    time_label: str,
) -> Dict[str, Any]:
    """Confirm an appointment for the provided date and time.

    Delegates to the existing confirm helper to send confirmation and follow-ups.
    """

    try:
        # Local import to avoid circular dependency
        from controllers.web_socket import _confirm_appointment  # type: ignore
        await _confirm_appointment(wa_id, db, date_iso, time_label)
        return {"status": "appointment_captured", "date": date_iso, "time": time_label}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def run_appointment_buttons_flow(
    db: Session,
    *,
    wa_id: str,
    btn_id: str | None = None,
    btn_text: str | None = None,
    btn_payload: str | None = None,
) -> Dict[str, Any]:
    """Handle appointment related buttons: book_appointment, request_callback, and time_* selections.

    Uses existing helpers in the websocket controller for date list and time confirmation.
    """

    try:
        normalized_id = (btn_id or "").strip().lower()
        normalized_text = (btn_text or "").strip().lower()
        normalized_payload = (btn_payload or "").strip().lower()

        # Book appointment
        if (
            normalized_id in {"book_appointment", "confirm_appointment"}
            or normalized_text in {"book an appointment", "book appointment", "book your appointment", "confirm appointment"}
            or normalized_payload in {"book an appointment", "book appointment", "book your appointment", "confirm appointment"}
        ):
            try:
                # If in treatment context, create lead immediately and send thank you
                from controllers.web_socket import appointment_state  # type: ignore
                st = appointment_state.get(wa_id) or {}
                flow_ctx = st.get("flow_context")
                if flow_ctx == "treatment":
                    # Send welcome message again from the same treatment number before proceeding
                    try:
                        from marketing.whatsapp_numbers import WHATSAPP_NUMBERS, TREATMENT_FLOW_ALLOWED_PHONE_IDS  # type: ignore
                        phone_id_for_welcome = (
                            st.get("treatment_flow_phone_id")
                            or st.get("incoming_phone_id")
                        )
                        if not phone_id_for_welcome and TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                            phone_id_for_welcome = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                        from_wa_for_welcome = None
                        if phone_id_for_welcome:
                            cfg_w = WHATSAPP_NUMBERS.get(str(phone_id_for_welcome)) if isinstance(WHATSAPP_NUMBERS, dict) else None
                            if cfg_w:
                                import re as _re
                                from_wa_for_welcome = _re.sub(r"\D", "", cfg_w.get("name", "")) or None
                        welcome_message = "Hi! Thanks for reaching out to Oliva Clinics. I'm your virtual assistant here to help you instantly."
                        await send_message_to_waid(
                            wa_id,
                            welcome_message,
                            db,
                            phone_id_hint=str(phone_id_for_welcome) if phone_id_for_welcome else None,
                            from_wa_id=from_wa_for_welcome,
                            schedule_followup=False,
                        )
                        # Mark treatment context to ensure subsequent steps stay on this number
                        st["flow_context"] = "treatment"
                        st["from_treatment_flow"] = True
                        if phone_id_for_welcome:
                            st["treatment_flow_phone_id"] = str(phone_id_for_welcome)
                            st["incoming_phone_id"] = str(phone_id_for_welcome)
                        appointment_state[wa_id] = st
                        print(f"[treatment_flow] DEBUG - Sent welcome on book_appointment tap using phone_id={phone_id_for_welcome}")
                        # Immediately prompt city selection to restart flow
                        try:
                            from marketing.city_selection import send_city_selection
                            await send_city_selection(db, wa_id=wa_id, phone_id_hint=str(phone_id_for_welcome) if phone_id_for_welcome else None)
                            print(f"[treatment_flow] DEBUG - Sent city selection after welcome on book_appointment tap (wa_id={wa_id})")
                        except Exception as e_city:
                            print(f"[treatment_flow] WARNING - Could not send city selection after book_appointment tap: {e_city}")
                    except Exception as e_welcome:
                        print(f"[treatment_flow] WARNING - Could not send welcome on book_appointment tap: {e_welcome}")

                    # Initialize is_duplicate flag to track if lead was a duplicate
                    is_duplicate = False
                    lead_res = None
                    customer_name = ""
                    try:
                        from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
                        from services.customer_service import get_customer_record_by_wa_id
                        from utils.flow_log import log_flow_event  # type: ignore
                        customer = get_customer_record_by_wa_id(db, wa_id)
                        customer_name = getattr(customer, "name", None) or ""
                        selected_concern = (st or {}).get("selected_concern")
                        appointment_details = {
                            "flow_type": "treatment_flow",
                            "treatment_selected": True,
                            "no_scheduling_required": True,
                            "selected_concern": selected_concern,
                        }
                        lead_res = await create_lead_for_appointment(
                            db=db,
                            wa_id=wa_id,
                            customer=customer,
                            appointment_details=appointment_details,
                            lead_status="PENDING",
                            appointment_preference="Treatment consultation - no specific appointment time requested",
                        )
                        # Check if lead was a duplicate
                        if isinstance(lead_res, dict):
                            if lead_res.get("duplicate") or lead_res.get("skipped"):
                                is_duplicate = True
                        # Mark flow completion for summary API
                        try:
                            _desc = "Treatment flow completed: Lead created and thank-you sent"
                            if is_duplicate:
                                _desc = f"Treatment flow completed: duplicate avoided (lead {lead_res.get('lead_id') if lead_res else 'N/A'})"
                            log_flow_event(
                                db,
                                flow_type="treatment",
                                step="result",
                                status_code=200,
                                wa_id=wa_id,
                                name=customer_name,
                                description=_desc,
                                response_json=json.dumps(lead_res, default=str) if lead_res is not None else None,
                            )
                        except Exception:
                            pass
                    except Exception:
                        # Log failure to help summary API
                        is_duplicate = True  # Treat exceptions as duplicates to avoid counting failed leads
                        try:
                            log_flow_event(
                                db,
                                flow_type="treatment",
                                step="result",
                                status_code=500,
                                wa_id=wa_id,
                                name=customer_name if customer_name else None,
                                description="Treatment flow failed while creating lead",
                            )
                        except Exception:
                            pass
                    
                    # Create appointment record for tracking ONLY if lead was NOT a duplicate
                    # This ensures we only count appointments where leads were successfully pushed to Zoho
                    if not is_duplicate:
                        try:
                            from services.referrer_service import referrer_service
                            from datetime import datetime as dt
                            # Get selected concern and other details from state
                            selected_concern = st.get("selected_concern") or "Treatment Consultation"
                            selected_city = st.get("selected_city")
                            selected_location = st.get("selected_location")
                            
                            # Determine center name and location
                            center_name = "Oliva Clinics"
                            location = selected_location or selected_city or "Multiple Locations"
                            if selected_city:
                                center_name = f"Oliva {selected_city}"
                            
                            # Create appointment record with today's date (appointment will be confirmed later)
                            # Use current date as appointment_date since no specific date was selected
                            today_str = dt.now().strftime("%Y-%m-%d")
                            appointment_record = referrer_service.create_appointment_booking(
                                db=db,
                                wa_id=wa_id,
                                appointment_date=today_str,
                                appointment_time="To be confirmed",
                                treatment_type=selected_concern
                            )
                            if appointment_record:
                                # Update center_name and location if we have better info
                                if selected_city or selected_location:
                                    try:
                                        appointment_record.center_name = center_name
                                        appointment_record.location = location
                                        db.commit()
                                        db.refresh(appointment_record)
                                        print(f"[treatment_flow] DEBUG - Appointment record created (non-duplicate lead): id={appointment_record.id}, wa_id={wa_id}")
                                    except Exception as e:
                                        print(f"[treatment_flow] WARNING - Could not update appointment record location: {e}")
                            else:
                                print(f"[treatment_flow] WARNING - Failed to create appointment record for wa_id={wa_id}")
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Could not create appointment record: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"[treatment_flow] DEBUG - Skipping appointment record creation (duplicate lead detected) for wa_id={wa_id}")
                    
                    # Thank you message - use the phone_id that triggered this flow
                    stored_phone_id = st.get("treatment_flow_phone_id")
                    phone_id_hint = stored_phone_id if stored_phone_id else None
                    if not phone_id_hint:
                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                        phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                    await send_message_to_waid(
                        wa_id,
                        # "✅ Thank you! Our team will contact you shortly to confirm your appointment.",
                        db,
                        phone_id_hint=str(phone_id_hint),
                    )
                    # Stop any follow-ups for completed flow (don't reset timer since flow is complete)
                    try:
                        from services.followup_service import mark_customer_replied as _mark_replied
                        from services.customer_service import get_customer_record_by_wa_id as _get_cust
                        _cust = _get_cust(db, wa_id)
                        if _cust:
                            _mark_replied(db, customer_id=_cust.id, reset_followup_timer=False)
                    except Exception:
                        pass
                    # Clear state
                    try:
                        if wa_id in appointment_state:
                            appointment_state.pop(wa_id, None)
                        # Also clear lead_appointment_state if present
                        from controllers.web_socket import lead_appointment_state  # type: ignore
                        if wa_id in lead_appointment_state:
                            lead_appointment_state.pop(wa_id, None)
                        print(f"[treatment_flow] DEBUG - Cleared all flow state for completed flow: wa_id={wa_id}")
                    except Exception:
                        pass
                    return {"status": "treatment_lead_created"}
                else:
                    # Non-treatment flows: route to city selection
                    st["flow_context"] = "treatment"
                    appointment_state[wa_id] = st
                    from controllers.components.lead_appointment_flow.city_selection import send_city_selection
                    result = await send_city_selection(db, wa_id=wa_id)
                    return {"status": "city_list_sent", "result": result}
            except Exception as e:
                return {"status": "failed", "error": str(e)[:200]}

        # Request a call back
        if (
            normalized_id == "request_callback"
            or normalized_text == "request a call back"
            or normalized_payload == "request a call back"
            or ("request" in normalized_text and ("call back" in normalized_text or "callback" in normalized_text))
            or ("request" in normalized_payload and ("call back" in normalized_payload or "callback" in normalized_payload))
        ):
            try:
                # Use the phone_id that triggered this flow
                from controllers.web_socket import appointment_state  # type: ignore
                st_cb = appointment_state.get(wa_id) or {}
                stored_phone_id_cb = st_cb.get("treatment_flow_phone_id")
                phone_id_hint_cb = stored_phone_id_cb if stored_phone_id_cb else None
                if not phone_id_hint_cb:
                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                    phone_id_hint_cb = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                await send_message_to_waid(
                    wa_id,
                    "📌 Thank you for your interest! One of our team members will contact you shortly to assist further.",
                    db,
                    phone_id_hint=str(phone_id_hint_cb),
                )
                # Stop any follow-ups for completed flow (don't reset timer since flow is complete)
                try:
                    from services.followup_service import mark_customer_replied as _mark_replied
                    from services.customer_service import get_customer_record_by_wa_id as _get_cust
                    _cust = _get_cust(db, wa_id)
                    if _cust:
                        _mark_replied(db, customer_id=_cust.id, reset_followup_timer=False)
                except Exception:
                    pass
                
                # Create lead in Zoho for callback request
                try:
                    from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
                    from services.customer_service import get_customer_record_by_wa_id
                    customer = get_customer_record_by_wa_id(db, wa_id)
                    
                    # Prepare appointment details for callback request
                    appointment_details = {
                        "flow_type": "treatment_flow",
                        "treatment_selected": True,
                        "callback_requested": True,
                        "no_scheduling_required": True
                    }
                    
                    lead_result = await create_lead_for_appointment(
                        db=db,
                        wa_id=wa_id,
                        customer=customer,
                        appointment_details=appointment_details,
                        lead_status="PENDING",
                        appointment_preference="Treatment consultation - callback requested"
                    )
                    print(f"[treatment_flow] DEBUG - Lead creation result (callback): {lead_result}")
                except Exception as e:
                    print(f"[treatment_flow] WARNING - Could not create lead (callback): {e}")
                    
                # Clear state after callback request
                try:
                    if wa_id in appointment_state:
                        appointment_state.pop(wa_id, None)
                    # Also clear lead_appointment_state if present
                    from controllers.web_socket import lead_appointment_state  # type: ignore
                    if wa_id in lead_appointment_state:
                        lead_appointment_state.pop(wa_id, None)
                    print(f"[treatment_flow] DEBUG - Cleared all flow state for callback request: wa_id={wa_id}")
                except Exception:
                    pass
            except Exception:
                pass
            return {"status": "callback_ack"}

        # Time selection
        time_map = {
            "time_10_00": "10:00 AM",
            "time_14_00": "2:00 PM",
            "time_18_00": "6:00 PM",
        }
        possible_time = (
            time_map.get(normalized_id)
            or (btn_text or "").strip()
            or (btn_payload or "").strip()
        )
        if (
            normalized_id.startswith("time_")
            or possible_time in ["10:00 AM", "2:00 PM", "6:00 PM"]
        ):
            try:
                from controllers.web_socket import appointment_state, send_date_list  # type: ignore
                time_label = time_map.get(normalized_id) or (btn_text or btn_payload or "").strip()
                date_iso = (appointment_state.get(wa_id) or {}).get("date")
                if date_iso and time_label:
                    result = await run_confirm_appointment_flow(
                        db,
                        wa_id=wa_id,
                        date_iso=date_iso,
                        time_label=time_label,
                    )
                    if result.get("status") == "appointment_captured":
                        return result
                # Need date first -> start from week selection
                await send_message_to_waid(wa_id, "Please select a week and then a date.", db)
                # Use TREATMENT FLOW specific week list (original function)
                from controllers.components.interactive_type import send_week_list  # type: ignore
                await send_week_list(db, wa_id)
                return {"status": "need_date_first"}
            except Exception as e:
                return {"status": "failed", "error": str(e)[:200]}

    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}

    return {"status": "skipped"}