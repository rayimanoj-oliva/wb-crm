from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import os
import re
import requests

from sqlalchemy.orm import Session

from marketing.whatsapp_numbers import get_number_config, WHATSAPP_NUMBERS
from config.constants import get_messages_url
from utils.ws_manager import manager


def _resolve_credentials(
    db: Session,
    *,
    wa_id: str,
    phone_id_hint: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve (access_token, phone_id) for treatment messages.

    Priority:
    1) Explicit phone_id_hint
    2) Stored `treatment_flow_phone_id` in appointment_state
    3) Env var TREATMENT_FLOW_PHONE_ID/WELCOME_PHONE_ID
    4) First configured number in WHATSAPP_NUMBERS
    """
    # 1) Hint
    if phone_id_hint:
        cfg = get_number_config(str(phone_id_hint))
        if cfg and cfg.get("token"):
            return cfg.get("token"), str(phone_id_hint)

    # 2) Stored state
    try:
        from controllers.web_socket import appointment_state  # type: ignore
        st = appointment_state.get(wa_id) or {}
        stored_phone_id = st.get("treatment_flow_phone_id")
        if stored_phone_id:
            cfg = get_number_config(str(stored_phone_id))
            if cfg and cfg.get("token"):
                return cfg.get("token"), str(stored_phone_id)
    except Exception:
        pass

    # 3) Env configured
    env_pid = os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WELCOME_PHONE_ID")
    if env_pid:
        cfg_env = get_number_config(str(env_pid))
        if cfg_env and cfg_env.get("token"):
            return cfg_env.get("token"), str(env_pid)

    # 4) First configured number (from mapping tokens)
    try:
        first_pid = next(iter(WHATSAPP_NUMBERS.keys()))
        cfg_first = get_number_config(str(first_pid))
        if cfg_first and cfg_first.get("token"):
            return cfg_first.get("token"), str(first_pid)
    except Exception:
        pass
    return None, None


def _display_from_for_phone_id(phone_id: Optional[str]) -> str:
    try:
        if not phone_id:
            return os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
        cfg = get_number_config(str(phone_id))
        return re.sub(r"\D", "", (cfg.get("name") or "")) if cfg else os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
    except Exception:
        return os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")


def send_mr_treatment(
    db: Session,
    *,
    wa_id: str,
    phone_id_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Send the mr_treatment template once and mark state to prevent duplicates."""
    access_token, phone_id = _resolve_credentials(db, wa_id=wa_id, phone_id_hint=phone_id_hint)
    if not access_token or not phone_id:
        return {"success": False, "error": "no_credentials"}

    from controllers.auto_welcome_controller import _send_template  # local import to avoid cycles
    lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
    resp = _send_template(
        wa_id=wa_id,
        template_name="mr_treatment",
        access_token=access_token,
        phone_id=phone_id,
        components=None,
        lang_code=lang_code,
    )
    if resp.status_code == 200:
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            st["mr_treatment_sent"] = True
            # If mr_treatment template contains concern buttons, mark them as sent
            # (Note: This assumes the template has buttons; adjust if template structure differs)
            st["concern_buttons_sent"] = True
            # Track pending template for one-time resend on free text
            from datetime import datetime as _dt
            st["pending_template"] = {"name": "mr_treatment", "ts": _dt.utcnow().isoformat(), "resend_done": False}
            appointment_state[wa_id] = st
        except Exception:
            pass
    try:
        awaitable = manager.broadcast({
            "from": _display_from_for_phone_id(phone_id),
            "to": wa_id,
            "type": "template" if resp.status_code == 200 else "template_error",
            "message": "mr_treatment sent" if resp.status_code == 200 else "mr_treatment failed",
            "timestamp": datetime.now().isoformat(),
        })
        # manager.broadcast is async; support both sync/async contexts
        if hasattr(awaitable, "__await__"):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(awaitable)
                else:
                    loop.run_until_complete(awaitable)
            except Exception:
                pass
    except Exception:
        pass
    return {"success": resp.status_code == 200, "status_code": resp.status_code}


def send_concern_buttons(
    db: Session,
    *,
    wa_id: str,
    phone_id_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Send Skin/Hair/Body concern buttons from treatment number."""
    access_token, phone_id = _resolve_credentials(db, wa_id=wa_id, phone_id_hint=phone_id_hint)
    if not access_token or not phone_id:
        return {"success": False, "error": "no_credentials"}

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
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
    resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if resp.status_code == 200:
        # Mark concern buttons as sent to prevent duplicates
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            st["concern_buttons_sent"] = True
            # Remember pending interactive so we can resend on free text
            from datetime import datetime as _dt
            st["pending_interactive"] = {"kind": "treatment_concerns", "ts": _dt.utcnow().isoformat(), "resend_done": False}
            appointment_state[wa_id] = st
        except Exception:
            pass
    try:
        awaitable = manager.broadcast({
            "from": _display_from_for_phone_id(phone_id),
            "to": wa_id,
            "type": "interactive",
            "message": "Please choose your area of concern:",
            "timestamp": datetime.now().isoformat(),
            "meta": {"kind": "buttons", "options": ["Skin", "Hair", "Body"]},
        })
        if hasattr(awaitable, "__await__"):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(awaitable)
                else:
                    loop.run_until_complete(awaitable)
            except Exception:
                pass
    except Exception:
        pass
    return {"success": resp.status_code == 200, "status_code": resp.status_code}


def send_next_actions(
    db: Session,
    *,
    wa_id: str,
    phone_id_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Send next actions: Book Appointment / Request a Call Back."""
    access_token, phone_id = _resolve_credentials(db, wa_id=wa_id, phone_id_hint=phone_id_hint)
    if not access_token or not phone_id:
        return {"success": False, "error": "no_credentials"}

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Please choose one of the following options:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "book_appointment", "title": "📅 Book an Appointment"}},
                    {"type": "reply", "reply": {"id": "request_callback", "title": "📞 Request a Call Back"}},
                ]
            },
        },
    }
    resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if resp.status_code == 200:
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            from datetime import datetime as _dt
            st["pending_interactive"] = {"kind": "next_actions", "ts": _dt.utcnow().isoformat(), "resend_done": False}
            appointment_state[wa_id] = st
        except Exception:
            pass
    try:
        awaitable = manager.broadcast({
            "from": _display_from_for_phone_id(phone_id),
            "to": wa_id,
            "type": "interactive",
            "message": "Please choose one of the following options:",
            "timestamp": datetime.now().isoformat(),
            "meta": {"kind": "buttons", "options": ["📅 Book an Appointment", "📞 Request a Call Back"]},
        })
        if hasattr(awaitable, "__await__"):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(awaitable)
                else:
                    loop.run_until_complete(awaitable)
            except Exception:
                pass
    except Exception:
        pass
    return {"success": resp.status_code == 200, "status_code": resp.status_code}


