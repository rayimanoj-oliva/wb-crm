from controllers.web_socket import manager  # reuse the same WS manager for UI updates

from sqlalchemy.orm import Session

from typing import Any, Dict
import os

from marketing.whatsapp_numbers import (
    TREATMENT_FLOW_ALLOWED_PHONE_IDS,
    WHATSAPP_NUMBERS,
    get_number_config,
)

from controllers.components.number_flows.mr_welcome.flow import run_mr_welcome_number_flow
from marketing.treament_flow import run_treament_flow
from services import customer_service, message_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from models.models import Message



def _is_allowed_marketing_number(value: Dict[str, Any], to_wa_id: str | None) -> bool:
    try:
        pid = (value or {}).get("metadata", {}).get("phone_number_id")
        if pid and str(pid) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
            return True
    except Exception:
        pass
    # match by last-10 digits of display number
    try:
        disp = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or (to_wa_id or "")
        import re as _re
        disp_digits = _re.sub(r"\D", "", disp or "")
        disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
        for pid, cfg in (WHATSAPP_NUMBERS or {}).items():
            if pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                if name_last10 and disp_last10 and name_last10 == disp_last10:
                    return True
    except Exception:
        pass
    return False


async def handle_marketing_event(db: Session, *, value: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a WhatsApp webhook value dict for the two treatment numbers only.
    This is designed to be called from the main webhook; no extra route is defined here.
    """
    messages = value.get("messages") or []
    contacts = value.get("contacts") or []
    if not messages or not contacts:
        return {"status": "ignored", "reason": "no_messages_or_contacts"}

    message = messages[0]
    contact = contacts[0]

    wa_id = contact.get("wa_id") or message.get("from")
    from_wa_id = message.get("from")
    to_wa_id = (value.get("metadata", {}) or {}).get("display_phone_number")
    message_type = message.get("type")
    message_id = message.get("id")
    timestamp = message.get("timestamp")

    # Gate: only handle our two treatment numbers
    if not _is_allowed_marketing_number(value, to_wa_id):
        return {"status": "ignored", "reason": "not_marketing_number"}

    # 1) Handle follow-up YES at highest priority (button_reply.id == followup_yes)
    if message_type == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") == "button_reply":
            btn = interactive.get("button_reply", {})
            btn_id = (btn.get("id") or "").strip().lower()
            if btn_id == "followup_yes":
                # Always restart treatment flow on follow-up YES for treatment numbers
                # Keep a short in-progress guard to avoid double-send within a few seconds
                try:
                    from controllers.web_socket import appointment_state  # type: ignore
                    from datetime import datetime, timedelta
                    st_lock = appointment_state.get(wa_id) or {}
                    ts_str = st_lock.get("mr_welcome_sending_ts")
                    ts_obj = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else None
                    if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=10):
                        return {"status": "skipped", "reason": "welcome_in_progress"}
                    # Clear previous run markers so flow starts from the beginning
                    st_lock.pop("mr_welcome_sent", None)
                    st_lock.pop("contact_confirm_sent", None)
                    st_lock["flow_context"] = "treatment"
                    st_lock["from_treatment_flow"] = True
                    try:
                        pid_meta = (value.get("metadata", {}) or {}).get("phone_number_id")
                        if pid_meta:
                            st_lock["treatment_flow_phone_id"] = str(pid_meta)
                    except Exception:
                        pass
                    st_lock["mr_welcome_sending_ts"] = datetime.utcnow().isoformat()
                    appointment_state[wa_id] = st_lock
                except Exception:
                    pass

                res = await run_mr_welcome_number_flow(
                    db,
                    wa_id=wa_id,
                    to_wa_id=to_wa_id,
                    message_id=message_id,
                    message_type=message_type,
                    timestamp=datetime_from_ts(timestamp),
                    customer=None,
                    value=value,
                )
                return {"status": "welcome_restart", **(res or {})}

        # For all other interactive types (e.g., city list replies), do not handle here;
        # allow main webhook to process via interactive_type_clean.
        try:
            print(f"[ws_marketing] DEBUG - Ignoring interactive type='{interactive.get('type')}' for wa_id={wa_id} to route via main handler")
        except Exception:
            pass
        return {"status": "ignored", "reason": "defer_interactive_to_main"}

    # Record last interaction to drive follow-up timers for both treatment numbers
    try:
        from services import customer_service
        from schemas.customer_schema import CustomerCreate
        from services.followup_service import mark_customer_replied
        cust = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=(contact.get("profile") or {}).get("name")))
        # Reset Follow-Up 1 window from last inbound interaction
        mark_customer_replied(db, customer_id=cust.id)
    except Exception:
        pass

    # 2) Delegate to treatment text prefill validator ONLY for text messages
    if message_type == "text":
        body_text = (message.get(message_type, {}) or {}).get("body", "") if isinstance(message.get(message_type, {}), dict) else ""
        message_ts = datetime_from_ts(timestamp)

        # Persist inbound message if not already saved
        try:
            existing_msg = db.query(Message).filter(Message.message_id == message_id).first()
        except Exception:
            existing_msg = None
        if not existing_msg:
            try:
                customer = customer_service.get_or_create_customer(
                    db,
                    CustomerCreate(wa_id=wa_id, name=(contact.get("profile") or {}).get("name")),
                )
            except Exception:
                customer = None
            try:
                inbound = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type="text",
                    body=body_text,
                    timestamp=message_ts,
                    customer_id=(customer.id if customer else None),
                )
                message_service.create_message(db, inbound)
            except Exception as e:
                print(f"[ws_marketing] WARNING - Could not persist treatment text message: {e}")

            try:
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": "text",
                    "message": body_text,
                    "timestamp": message_ts.isoformat(),
                    "message_id": message_id,
                    "meta": {
                        "flow": "treatment",
                        "action": "customer_message",
                        "source": "marketing_handler",
                    },
                })
            except Exception as e:
                print(f"[ws_marketing] WARNING - Could not broadcast treatment text message: {e}")

        res2 = await run_treament_flow(
            db,
            message_type=message_type,
            message_id=message_id,
            from_wa_id=from_wa_id,
            to_wa_id=to_wa_id,
            body_text=body_text,
            timestamp=message_ts,
            customer=None,
            wa_id=wa_id,
            value=value,
            sender_name=(contact.get("profile") or {}).get("name"),
        )
        try:
            print(f"[ws_marketing] DEBUG - handled text in marketing handler for wa_id={wa_id}")
        except Exception:
            pass
        return {"status": "handled", **(res2 or {})}

    # Non-text messages fall through to main handler
    return {"status": "ignored", "reason": "non_text_interactive_deferred"}


def datetime_from_ts(ts: Any):
    from datetime import datetime
    try:
        return datetime.fromtimestamp(int(ts))
    except Exception:
        return datetime.utcnow()


