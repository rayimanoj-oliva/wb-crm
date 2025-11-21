from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import os
import asyncio

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.db import SessionLocal
from services import whatsapp_service, customer_service, message_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from config.constants import get_messages_url


# Follow-Up 1 content and timing
FOLLOW_UP_1_DELAY_MINUTES = 5
FOLLOW_UP_1_TEXT = (
    "👋 Hi! Just checking in — are we still connected?\n\n"
    "Reply to continue. 💬\n\n"
)


async def send_follow_up1(
    db: Session,
    *,
    wa_id: str,
    from_wa_id: str = "917729992376",
    phone_id_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Send Follow-Up 1 as an interactive message with a single ✅ Yes button."""
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    access_token = token_obj.token
    phone_id = phone_id_hint or os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    if phone_id_hint:
        try:
            from marketing.whatsapp_numbers import WHATSAPP_NUMBERS  # type: ignore

            cfg = (WHATSAPP_NUMBERS or {}).get(str(phone_id_hint)) or {}
            token_override = cfg.get("token")
            if token_override:
                access_token = token_override
                phone_id = str(phone_id_hint)
        except Exception:
            phone_id = str(phone_id_hint)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": FOLLOW_UP_1_TEXT},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "followup_yes", "title": "✅ Yes"}},
                ]
            },
        },
    }

    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send follow-up 1 interactive: {res.text}")

    message_id = res.json().get("messages", [{}])[0].get("id")

    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    message_data = MessageCreate(
        message_id=message_id or f"outbound_{datetime.utcnow().timestamp()}",
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="interactive",
        body="Follow-Up 1 (Yes)",
        timestamp=datetime.utcnow(),
        customer_id=customer.id,
    )
    message_service.create_message(db, message_data)

    return {"success": True, "message_id": message_id}


async def schedule_follow_up1_after_welcome(
    wa_id: str,
    sent_at: datetime,
) -> None:
    """Wait FOLLOW_UP_1_DELAY_MINUTES, then send Follow-Up 1 if user hasn't replied.

    Conditions to send:
    - User is still in lead appointment flow
    - No interaction recorded after the welcome `sent_at`
    """
    try:
        await asyncio.sleep(FOLLOW_UP_1_DELAY_MINUTES * 60)

        # Open a fresh DB session inside the scheduled task
        db: Optional[Session] = None
        try:
            db = SessionLocal()

            # Ensure user is still in lead appointment flow
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                state = (lead_appointment_state.get(wa_id) or {})
                if state.get("flow_context") != "lead_appointment":
                    return
            except Exception:
                # If state can't be checked, be conservative and skip
                return

            cust = customer_service.get_customer_record_by_wa_id(db, wa_id)
            if not cust:
                return

            # If user interacted after welcome, skip sending follow-up
            if cust.last_interaction_time and cust.last_interaction_time > sent_at:
                return

            # Determine phone context for follow-up send
            phone_id_hint = None
            from_wa_display = os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore

                state = (lead_appointment_state.get(wa_id) or {})
                phone_id_hint = state.get("lead_phone_id")
                from_wa_display = state.get("lead_display_number", from_wa_display)
            except Exception:
                pass

            # Send Follow-Up 1 now
            await send_follow_up1(
                db,
                wa_id=wa_id,
                from_wa_id=from_wa_display,
                phone_id_hint=str(phone_id_hint) if phone_id_hint else None,
            )

            # Chain Follow-Up 2 scheduling (30 minutes after FU1 if still no reply)
            try:
                from .follow_up2 import schedule_follow_up2_after_follow_up1
                fu1_sent_at = datetime.utcnow()
                asyncio.create_task(schedule_follow_up2_after_follow_up1(wa_id, fu1_sent_at))
            except Exception:
                pass

        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass
    except Exception:
        # Swallow exceptions to avoid crashing background task
        return


async def schedule_follow_up1_after_not_now(
    wa_id: str,
    sent_at: datetime,
) -> None:
    """Wait FOLLOW_UP_1_DELAY_MINUTES after 'Not Now' message, then send Follow-Up 1.

    This is specifically for the 'Not Now' follow-up sequence.
    After sending Follow-Up 1, it will schedule Follow-Up 2, which will then create the lead.
    """
    try:
        await asyncio.sleep(FOLLOW_UP_1_DELAY_MINUTES * 60)

        # Open a fresh DB session inside the scheduled task
        db: Optional[Session] = None
        try:
            db = SessionLocal()

            # Ensure user is still in "Not Now" follow-up sequence
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                state = (lead_appointment_state.get(wa_id) or {})
                if not state.get("not_now_followup_sequence"):
                    return
            except Exception:
                # If state can't be checked, be conservative and skip
                return

            cust = customer_service.get_customer_record_by_wa_id(db, wa_id)
            if not cust:
                return

            # If user interacted after "Not Now" message, skip sending follow-up
            if cust.last_interaction_time and cust.last_interaction_time > sent_at:
                return

            phone_id_hint = None
            from_wa_display = os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore

                state = (lead_appointment_state.get(wa_id) or {})
                phone_id_hint = state.get("lead_phone_id") or state.get("treatment_flow_phone_id")
                from_wa_display = state.get("lead_display_number", from_wa_display)
            except Exception:
                pass

            # Send Follow-Up 1 now
            await send_follow_up1(
                db,
                wa_id=wa_id,
                from_wa_id=from_wa_display,
                phone_id_hint=str(phone_id_hint) if phone_id_hint else None,
            )

            # Chain Follow-Up 2 scheduling (after FU1 if still no reply)
            # Follow-Up 2 will create the lead after sending
            try:
                from .follow_up2 import schedule_follow_up2_after_follow_up1
                fu1_sent_at = datetime.utcnow()
                asyncio.create_task(schedule_follow_up2_after_follow_up1(wa_id, fu1_sent_at))
            except Exception:
                pass

        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass
    except Exception:
        # Swallow exceptions to avoid crashing background task
        return


