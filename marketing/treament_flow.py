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

        # 3) Prefill detection for mr_welcome (also trigger on simple greetings like "hi")
        prefill_regexes = [
            r"^hi,?\s*oliva\s+i\s+want\s+to\s+know\s+more\s+about\s+services\s+in\s+[a-z\s]+,\s*[a-z\s]+\s+clinic$",
            r"^hi,?\s*oliva\s+i\s+want\s+to\s+know\s+more\s+about\s+your\s+services$",
            # greetings
            r"^hi$",
            r"^hello$",
            r"^hlo$",
        ]
        prefill_detected = any(re.match(rx, normalized_body, flags=re.IGNORECASE) for rx in prefill_regexes)
        
        if prefill_detected:
            # If mr_welcome was already dispatched very recently by the dedicated number handler, skip to avoid duplicates
            skip_prefill_restart = False
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                from datetime import datetime as _dt, timedelta as _td
                st_existing = appointment_state.get(wa_id) or {}
                ts_str_existing = st_existing.get("mr_welcome_sending_ts")
                ts_obj_existing = _dt.fromisoformat(ts_str_existing) if isinstance(ts_str_existing, str) else None
                recently_sent = bool(ts_obj_existing and (_dt.utcnow() - ts_obj_existing) < _td(seconds=30))
                if bool(st_existing.get("mr_welcome_sent")) or recently_sent:
                    skip_prefill_restart = True
            except Exception:
                skip_prefill_restart = False

            if skip_prefill_restart:
                try:
                    print(f"[treatment_flow] DEBUG - Prefill skipped because mr_welcome already handled (wa_id={wa_id})")
                except Exception:
                    pass
                return {"status": "skipped", "message_id": message_id, "reason": "mr_welcome_already_sent"}

            # Clear stale state to allow flow restart when customer sends a starting point message
            try:
                from controllers.state.memory import clear_flow_state_for_restart
                clear_flow_state_for_restart(wa_id)
                print(f"[treatment_flow] DEBUG - Cleared stale state for new flow start (prefill detected): wa_id={wa_id}")
            except Exception as e:
                print(f"[treatment_flow] WARNING - Could not clear stale state: {e}")
            # Restrict treatment flow to only allowed phone numbers
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
            
            # Only proceed if this is an allowed phone number
            if not is_allowed:
                display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                print(f"[treatment_flow] DEBUG - Treatment flow blocked for phone_id: {phone_id_meta}, display_number: {display_num} (not in allowed list)")
                return {"status": "skipped", "message_id": message_id, "reason": "phone_number_not_allowed"}
            
            # Idempotency lock: avoid double mr_welcome when multiple handlers race
            # Check if mr_welcome was already sent by another handler (e.g., run_mr_welcome_number_flow)
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                from datetime import datetime, timedelta
                st_lock = appointment_state.get(wa_id) or {}
                # First check if mr_welcome was already sent - if so, skip sending again
                if bool(st_lock.get("mr_welcome_sent")):
                    # Check timestamp to see if it was sent very recently (within 10 seconds)
                    ts_str = st_lock.get("mr_welcome_sending_ts")
                    ts_obj = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else None
                    if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=10):
                        print(f"[treatment_flow] DEBUG - Skipping duplicate mr_welcome: already sent by another handler (wa_id={wa_id})")
                        return {"status": "skipped", "message_id": message_id, "reason": "mr_welcome_already_sent"}
                # Check if mr_welcome is currently being sent (within 10 seconds) to prevent race conditions
                ts_str = st_lock.get("mr_welcome_sending_ts")
                ts_obj = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else None
                if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=10):
                    return {"status": "skipped", "message_id": message_id, "reason": "mr_welcome_in_progress"}
                # Set sending timestamp to prevent concurrent sends
                st_lock["mr_welcome_sending_ts"] = datetime.utcnow().isoformat()
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
                    lang_code_prefill = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                    body_components_prefill = [{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": (sender_name or wa_id or "there")}
                        ],
                    }]
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template_attempt",
                            "message": "Sending mr_welcome...",
                            "params": {"body_param_1": (sender_name or wa_id or "there"), "lang": lang_code_prefill, "phone_id": phone_id_prefill},
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass

                    # Local import to avoid circulars
                    from controllers.auto_welcome_controller import _send_template

                    resp_prefill = _send_template(
                        wa_id=wa_id,
                        template_name="mr_welcome",
                        access_token=access_token_prefill,
                        phone_id=phone_id_prefill,
                        components=body_components_prefill,
                        lang_code=lang_code_prefill,
                    )
                    # Broadcast result to ChatWindow
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_prefill.status_code == 200 else "template_error",
                            "message": "mr_welcome sent" if resp_prefill.status_code == 200 else "mr_welcome failed",
                            **({"status_code": resp_prefill.status_code} if resp_prefill.status_code != 200 else {}),
                            **({"error": (resp_prefill.text[:500] if isinstance(resp_prefill.text, str) else str(resp_prefill.text))} if resp_prefill.status_code != 200 else {}),
                            "meta": {"phone_id": phone_id_prefill, "template": "mr_welcome"},
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
                    if resp_prefill.status_code == 200:
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template",
                                "message": "mr_welcome sent",
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                        # Schedule follow-up only for mr_welcome
                        try:
                            from services.followup_service import schedule_next_followup as _schedule, FOLLOW_UP_1_DELAY_MINUTES
                            from services.customer_service import get_customer_record_by_wa_id as _get_c
                            _cust = _get_c(db, wa_id)
                            if _cust:
                                _schedule(db, customer_id=_cust.id, delay_minutes=FOLLOW_UP_1_DELAY_MINUTES, stage_label="mr_welcome_sent")
                                print(f"[treatment_flow] INFO - Scheduled follow-up for customer {_cust.id} (wa_id: {wa_id}) after mr_welcome sent")
                            else:
                                print(f"[treatment_flow] WARNING - Could not find customer to schedule follow-up for wa_id: {wa_id}")
                        except Exception as e:
                            print(f"[treatment_flow] ERROR - Failed to schedule follow-up for {wa_id}: {e}")
                            import traceback
                            traceback.print_exc()

                        # Do NOT send mr_treatment here; it will be sent after city selection

                        # Mark context and set treatment flag; also mark mr_welcome_sent for idempotency
                        try:
                            from controllers.web_socket import appointment_state  # type: ignore
                            st = appointment_state.get(wa_id) or {}
                            st["flow_context"] = "treatment"
                            st["from_treatment_flow"] = True
                            st["mr_welcome_sent"] = True
                            appointment_state[wa_id] = st
                        except Exception:
                            pass

                        # Build and send name/phone confirmation with Yes/No
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
                                f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*"
                            )
                            # Ensure confirmation text is sent via the same phone_id used for the template
                            try:
                                from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                                st0 = _appt_state.get(wa_id) or {}
                                if not st0.get("contact_confirm_sent"):
                                    await send_message_to_waid(wa_id, confirm_msg, db, phone_id_hint=phone_id_prefill)
                                    st0["contact_confirm_sent"] = True
                                    _appt_state[wa_id] = st0
                            except Exception:
                                await send_message_to_waid(wa_id, confirm_msg, db, phone_id_hint=phone_id_prefill)

                            access_token, phone_id = _resolve_credentials_for_value()
                            if access_token:
                                headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
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
                                    _resp_btn = requests.post(get_messages_url(phone_id), headers=headers, json=payload_btn)
                                    try:
                                        print(f"[treatment_flow] DEBUG - confirm buttons sent phone_id={phone_id} status={_resp_btn.status_code}")
                                    except Exception:
                                        pass
                                except Exception as _e_btn:
                                    print(f"[treatment_flow] ERROR - confirm buttons post failed: {_e_btn}")
                                # Broadcast Yes/No buttons to websocket UI
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "interactive",
                                        "message": "Are your name and contact number correct? ",
                                        "timestamp": datetime.now().isoformat(),
                                        "meta": {"kind": "buttons", "options": ["Yes", "No"]},
                                    })
                                except Exception:
                                    pass
                                # Mark that we are awaiting an interactive response
                                try:
                                    from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                                    st_expect = _appt_state.get(wa_id) or {}
                                    st_expect["treatment_expect_interactive"] = "contact_confirmation"
                                    _appt_state[wa_id] = st_expect
                                except Exception:
                                    pass
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Could not send confirmation: {e}")

                        handled_text = True
                        return {"status": "awaiting_confirmation", "message_id": message_id}
                    else:
                        # SKIP mr_treatment fallback to avoid duplicates during correction/city paths
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template_error",
                                "message": "mr_welcome failed (fallback skipped)",
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                        handled_text = True
                        return {"status": "welcome_failed", "message_id": message_id}
                else:
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template_error",
                            "message": "mr_welcome not sent: no WhatsApp token",
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
    if topic in {"skin", "hair", "body"}:
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
            if access_token2:
                from controllers.auto_welcome_controller import _send_template
                lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                if topic == "skin":
                    resp_skin = _send_template(wa_id=wa_id, template_name="skin_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_skin.status_code == 200 else "template_error",
                            "message": "skin_treat_flow sent" if resp_skin.status_code == 200 else "skin_treat_flow failed",
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
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_hair.status_code == 200 else "template_error",
                            "message": "hair_treat_flow sent" if resp_hair.status_code == 200 else "hair_treat_flow failed",
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
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_body.status_code == 200 else "template_error",
                            "message": "body_treat_flow sent" if resp_body.status_code == 200 else "body_treat_flow failed",
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
        except Exception:
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
            except Exception:
                pass
            try:
                if wa_id not in lead_appointment_state:
                    lead_appointment_state[wa_id] = {}
                lead_appointment_state[wa_id]["selected_concern"] = selected_concern_label
            except Exception:
                pass
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

                lang_code_book = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                from controllers.auto_welcome_controller import _send_template
                resp_book = _send_template(
                    wa_id=wa_id,
                    template_name="booking_appoint",
                    access_token=access_token_book,
                    phone_id=str(phone_id_book),
                    components=None,
                    lang_code=lang_code_book,
                )
                try:
                    await manager.broadcast({
                        "from": to_wa_id,
                        "to": wa_id,
                        "type": "template" if resp_book.status_code == 200 else "template_error",
                        "message": "booking_appoint sent" if resp_book.status_code == 200 else "booking_appoint failed",
                        **({"status_code": resp_book.status_code} if resp_book.status_code != 200 else {}),
                    })
                except Exception:
                    pass
                # Do NOT send thank-you here; send it only after the user clicks "Book an Appointment"
        except Exception:
            pass

        try:
            token_entry3 = get_latest_token(db)
            if token_entry3 and token_entry3.token:
                access_token3 = token_entry3.token
                headers3 = {"Authorization": f"Bearer {access_token3}", "Content-Type": "application/json"}
                # Use stored phone_id from flow start, or fallback to first allowed number
                try:
                    from controllers.web_socket import appointment_state  # type: ignore
                    st = appointment_state.get(wa_id) or {}
                    stored_phone_id = st.get("treatment_flow_phone_id")
                    if stored_phone_id:
                        phone_id3 = stored_phone_id
                    else:
                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                        phone_id3 = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                except Exception:
                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                    phone_id3 = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                payload_buttons = {
                    "messaging_product": "whatsapp",
                    "to": wa_id,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": "Please choose one of the following options:"},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 📅 Book an Appointment"}},
                                {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde 📞 Request a Call Back"}},
                            ]
                        },
                    },
                }
                requests.post(get_messages_url(phone_id3), headers=headers3, json=payload_buttons)
                try:
                    from controllers.web_socket import appointment_state as _appt_state  # type: ignore
                    st_expect = _appt_state.get(wa_id) or {}
                    st_expect["treatment_expect_interactive"] = "next_actions"
                    _appt_state[wa_id] = st_expect
                except Exception:
                    pass
                return {"status": "next_actions_sent", "message_id": message_id}
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
            normalized_id == "book_appointment"
            or normalized_text in {"book an appointment", "book appointment"}
            or normalized_payload in {"book an appointment", "book appointment"}
        ):
            try:
                # If in treatment context, create lead immediately and send thank you
                from controllers.web_socket import appointment_state  # type: ignore
                st = appointment_state.get(wa_id) or {}
                flow_ctx = st.get("flow_context")
                if flow_ctx == "treatment":
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
                        # Mark flow completion for summary API
                        try:
                            _desc = "Treatment flow completed: Lead created and thank-you sent"
                            try:
                                if isinstance(lead_res, dict) and lead_res.get("duplicate"):
                                    _desc = f"Treatment flow completed: duplicate avoided (lead {lead_res.get('lead_id')})"
                            except Exception:
                                pass
                            log_flow_event(
                                db,
                                flow_type="treatment",
                                step="result",
                                status_code=200,
                                wa_id=wa_id,
                                name=customer_name,
                                description=_desc,
                            )
                        except Exception:
                            pass
                    except Exception:
                        # Log failure to help summary API
                        try:
                            log_flow_event(
                                db,
                                flow_type="treatment",
                                step="result",
                                status_code=500,
                                wa_id=wa_id,
                                name=customer_name if 'customer_name' in locals() else None,
                                description="Treatment flow failed while creating lead",
                            )
                        except Exception:
                            pass
                    # Thank you message - use the phone_id that triggered this flow
                    stored_phone_id = st.get("treatment_flow_phone_id")
                    phone_id_hint = stored_phone_id if stored_phone_id else None
                    if not phone_id_hint:
                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                        phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                    await send_message_to_waid(
                        wa_id,
                        "✅ Thank you! Our team will contact you shortly to confirm your appointment.",
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