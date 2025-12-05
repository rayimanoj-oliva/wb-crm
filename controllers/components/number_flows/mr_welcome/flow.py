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

        # mr_welcome template and confirmation buttons removed
        # Mark state so downstream handlers continue the flow consistently
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            st["from_treatment_flow"] = True
            st["flow_context"] = "treatment"
            st["treatment_flow_phone_id"] = str(phone_id)
            appointment_state[wa_id] = st
        except Exception:
            pass
        return {"status": "skipped", "message_id": message_id}

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

