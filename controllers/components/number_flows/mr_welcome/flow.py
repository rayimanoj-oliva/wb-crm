from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import os

from sqlalchemy.orm import Session
from config.constants import get_messages_url
import requests
import asyncio

from services.whatsapp_service import get_latest_token
from marketing.whatsapp_numbers import get_number_config
from utils.ws_manager import manager
from services import flow_config_service


async def run_mr_welcome_number_flow(
    db: Session,
    *,
    wa_id: str,
    to_wa_id: str,
    message_id: str,
    message_type: str,
    timestamp: datetime,
    customer: Any,
    value: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send the mr_welcome template for messages received on the dedicated number.

    Returns a status dict and short-circuits other flows when successful.
    """

    try:
        phone_number_id = None
        try:
            phone_number_id = (value or {}).get("metadata", {}).get("phone_number_id")
        except Exception:
            phone_number_id = None

        is_flow_live = True
        try:
            is_flow_live = flow_config_service.is_flow_live_for_number(
                db,
                phone_number_id=phone_number_id,
                display_number=to_wa_id,
            )
        except Exception as e:
            print(f"[mr_welcome_flow] WARNING - Could not verify flow config: {e}")
            is_flow_live = True

        if not is_flow_live:
            print(f"[mr_welcome_flow] INFO - Flow disabled for phone={phone_number_id or to_wa_id}; skipping welcome automation")
            return {"status": "flow_disabled", "message_id": message_id}

        # Resolve credentials prioritizing mapping by phone_number_id, then env override, then DB/env fallback
        def _resolve_credentials() -> tuple[str | None, str | None]:
            # A) webhook phone_number_id → mapping
            try:
                pid_meta = (value or {}).get("metadata", {}).get("phone_number_id")
                if pid_meta:
                    cfg = get_number_config(str(pid_meta))
                    if cfg and cfg.get("token"):
                        return cfg.get("token"), str(pid_meta)
            except Exception:
                pass
            # A2) Match display phone number (to_wa_id) against mapping names
            try:
                import re as _re
                disp_digits = _re.sub(r"\D", "", str(to_wa_id or ""))
                if disp_digits:
                    from marketing.whatsapp_numbers import WHATSAPP_NUMBERS as _MAP
                    for _pid, _cfg in (_MAP or {}).items():
                        name_digits = _re.sub(r"\D", "", (_cfg.get("name") or ""))
                        if name_digits and name_digits.endswith(disp_digits) and _cfg.get("token"):
                            return _cfg.get("token"), str(_pid)
            except Exception:
                pass
            # B) Env override for welcome (falls back to treatment flow id if provided)
            pid_env = os.getenv("WELCOME_PHONE_ID") or os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WHATSAPP_PHONE_ID")
            if pid_env:
                cfg2 = get_number_config(str(pid_env))
                if cfg2 and cfg2.get("token"):
                    return cfg2.get("token"), str(pid_env)
            # C) Final fallback: DB token + env/default phone id
            t = get_latest_token(db)
            if t and getattr(t, "token", None):
                return t.token, (os.getenv("WHATSAPP_PHONE_ID", "367633743092037"))
            return None, None

        access_token, phone_id = _resolve_credentials()
        if not access_token or not phone_id:
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
            return {"status": "welcome_failed", "message_id": message_id}

        # Idempotency check: prevent duplicate sends if already sent or currently sending
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            from datetime import datetime as _dt, timedelta
            st_check = appointment_state.get(wa_id) or {}
            # Strong guard: if mr_welcome was ever marked as sent in this session, do NOT send again
            if bool(st_check.get("mr_welcome_sent")):
                print(f"[mr_welcome_flow] DEBUG - Skipping mr_welcome: flag mr_welcome_sent=True (wa_id={wa_id})")
                return {"status": "welcome_already_sent", "message_id": message_id}
            # Check if currently being sent (race condition prevention)
            ts_str = st_check.get("mr_welcome_sending_ts")
            ts_obj = _dt.fromisoformat(ts_str) if isinstance(ts_str, str) else None
            if ts_obj and (_dt.utcnow() - ts_obj) < timedelta(seconds=10):
                print(f"[mr_welcome_flow] DEBUG - Skipping duplicate mr_welcome: currently sending (wa_id={wa_id})")
                return {"status": "welcome_in_progress", "message_id": message_id}
            # Set sending timestamp to prevent concurrent sends
            st_check["mr_welcome_sending_ts"] = _dt.utcnow().isoformat()
            appointment_state[wa_id] = st_check
        except Exception:
            pass

        # Use existing helper to send templates consistently
        from controllers.auto_welcome_controller import _send_template  # local import to avoid circulars

        # Optional: personalize with name if available via a single body param
        def _extract_profile_name(_value: Optional[Dict[str, Any]]) -> Optional[str]:
            try:
                contacts = (_value or {}).get("contacts") or []
                if isinstance(contacts, list) and contacts:
                    prof = (contacts[0] or {}).get("profile") or {}
                    nm = (prof.get("name") or "").strip()
                    if nm:
                        return nm
            except Exception:
                pass
            try:
                prof = (_value or {}).get("profile") or {}
                nm = (prof.get("name") or "").strip()
                if nm:
                    return nm
            except Exception:
                pass
            return None

        name_hint = _extract_profile_name(value) or (getattr(customer, "name", None) or None)
        body_components = [{
            "type": "body",
            "parameters": [
                {"type": "text", "text": name_hint or "there"}
            ],
        }]

        # Notify UI that we're attempting to send the template
        try:
            await manager.broadcast({
                "from": to_wa_id,
                "to": wa_id,
                "type": "template_attempt",
                "message": "Sending mr_welcome...",
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass

        lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
        resp = _send_template(
            wa_id=wa_id,
            template_name="mr_welcome",
            access_token=access_token,
            phone_id=phone_id,
            components=body_components,
            lang_code=lang_code,
        )

        try:
            await manager.broadcast({
                "from": to_wa_id,
                "to": wa_id,
                "type": "template" if resp.status_code == 200 else "template_error",
                "message": "mr_welcome sent" if resp.status_code == 200 else "mr_welcome failed",
                **({"status_code": resp.status_code} if resp.status_code != 200 else {}),
                "meta": {"phone_id": phone_id},
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass

        if resp.status_code == 200:
            # After template is sent, immediately send confirmation prompt from the same number.
            try:
                # Prepare name and phone display
                display_name = name_hint or getattr(customer, "name", None) or "there"
                import re as _re
                digits = _re.sub(r"\D", "", wa_id or "")
                last10 = digits[-10:] if len(digits) >= 10 else None
                display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id

                # 1) Send the confirmation text using the same phone_id
                try:
                    from utils.whatsapp import send_message_to_waid as _send_text
                    await _send_text(wa_id, f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*", db, phone_id_hint=str(phone_id))
                except Exception:
                    pass

                # 2) Send Yes/No buttons for confirmation from the same number
                try:
                    headers_btn = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
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
                    requests.post(get_messages_url(str(phone_id)), headers=headers_btn, json=payload_btn)
                except Exception:
                    pass

                # Mark state so downstream handlers continue the flow consistently
                try:
                    from controllers.web_socket import appointment_state  # type: ignore
                    st = appointment_state.get(wa_id) or {}
                    st["from_treatment_flow"] = True
                    st["flow_context"] = "treatment"
                    st["mr_welcome_sent"] = True
                    st["treatment_flow_phone_id"] = str(phone_id)
                    st["contact_confirm_sent"] = True
                    appointment_state[wa_id] = st
                except Exception:
                    pass

                # Schedule follow-up only for mr_welcome (same as treatment_flow.py)
                try:
                    from services.followup_service import schedule_next_followup as _schedule, FOLLOW_UP_1_DELAY_MINUTES
                    from services.customer_service import get_customer_record_by_wa_id as _get_c
                    _cust = _get_c(db, wa_id)
                    if _cust:
                        _schedule(db, customer_id=_cust.id, delay_minutes=FOLLOW_UP_1_DELAY_MINUTES, stage_label="mr_welcome_sent")
                        print(f"[mr_welcome_flow] INFO - Scheduled follow-up for customer {_cust.id} (wa_id: {wa_id}) after mr_welcome sent")
                    else:
                        print(f"[mr_welcome_flow] WARNING - Could not find customer to schedule follow-up for wa_id: {wa_id}")
                except Exception as e:
                    print(f"[mr_welcome_flow] ERROR - Failed to schedule follow-up for {wa_id}: {e}")
                    import traceback
                    traceback.print_exc()
            except Exception:
                pass
            return {"status": "welcome_sent", "message_id": message_id}
        return {"status": "welcome_failed", "message_id": message_id}

    except Exception as e:
        try:
            await manager.broadcast({
                "from": to_wa_id,
                "to": wa_id,
                "type": "template_error",
                "message": f"mr_welcome exception: {e}",
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass
        return {"status": "welcome_failed", "message_id": message_id}

