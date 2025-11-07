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
FOLLOW_UP_1_DELAY_MINUTES = 2
FOLLOW_UP_1_TEXT = (
    "👋 Hi! Just checking in — are we still connected?\n\n"
    "Reply to continue. 💬\n\n"
)


async def send_follow_up1(db: Session, *, wa_id: str, from_wa_id: str = "917729992376") -> Dict[str, Any]:
    """Send Follow-Up 1 as an interactive message with a single ✅ Yes button."""
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    headers = {
        "Authorization": f"Bearer {token_obj.token}",
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

    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
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


async def schedule_follow_up1_after_welcome(wa_id: str, sent_at: datetime) -> None:
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

            # Send Follow-Up 1 now
            await send_follow_up1(db, wa_id=wa_id)

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


async def schedule_follow_up1_after_not_now(wa_id: str, sent_at: datetime) -> None:
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

            # Send Follow-Up 1 now
            await send_follow_up1(db, wa_id=wa_id)

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


