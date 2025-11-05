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

        # Use existing helper to send templates consistently
        from controllers.auto_welcome_controller import _send_template  # local import to avoid circulars

        # Optional: personalize with name if available via a single body param
        body_components = [{
            "type": "body",
            "parameters": [
                {"type": "text", "text": getattr(customer, "name", None) or wa_id or "there"}
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
            # After welcome: send confirmation text and Yes/No buttons via the SAME phone_id
            try:
                try:
                    from controllers.web_socket import appointment_state  # type: ignore
                    st = appointment_state.get(wa_id) or {}
                    display_name = getattr(customer, "name", None) or "there"
                    import re as _re
                    digits = _re.sub(r"\D", "", wa_id)
                    last10 = digits[-10:] if len(digits) >= 10 else None
                    display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
                    confirm_msg = (
                        f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*"
                    )
                    # Ensure template appears first, then the text, then the buttons
                    try:
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass
                    from utils.whatsapp import send_message_to_waid as _send_text
                    await _send_text(wa_id, confirm_msg, db, phone_id_hint=str(phone_id))
                    # Broadcast confirm text to websocket for dashboard
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "text",
                            "message": confirm_msg,
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
                    st["contact_confirm_sent"] = True
                    st["from_treatment_flow"] = True
                    st["flow_context"] = "treatment"
                    appointment_state[wa_id] = st
                except Exception:
                    pass
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
                # Try to send interactive buttons (retry once if needed)
                _btn_ok = False
                for _i in range(2):
                    try:
                        try:
                            await asyncio.sleep(0.3 if _i == 0 else 0.8)
                        except Exception:
                            pass
                        _resp_btn = requests.post(get_messages_url(phone_id), headers=headers_btn, json=payload_btn)
                        try:
                            print(f"[mr_welcome_flow] DEBUG - confirm buttons attempt={_i+1} phone_id={phone_id} status={_resp_btn.status_code}")
                        except Exception:
                            pass
                        if getattr(_resp_btn, "status_code", 0) == 200:
                            _btn_ok = True
                            break
                    except Exception as _e_btn:
                        print(f"[mr_welcome_flow] ERROR - confirm buttons post failed attempt={_i+1}: {_e_btn}")
                # Also broadcast to UI so operators see the step even if WA delays
                try:
                    await manager.broadcast({
                        "from": to_wa_id,
                        "to": wa_id,
                        "type": "interactive",
                        "message": "Are your name and contact number correct? ",
                        "timestamp": datetime.now().isoformat(),
                        "meta": {"kind": "buttons", "options": ["Yes", "No"], "sent_ok": _btn_ok},
                    })
                except Exception:
                    pass
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


