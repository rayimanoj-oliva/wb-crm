from datetime import datetime
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


FOLLOW_UP_2_DELAY_MINUTES = 30
FOLLOW_UP_2_TEXT = (
    "No problem! You can reach out anytime to schedule your appointment.\n\n"
    "✅ 8 lakh+ clients have trusted Oliva & experienced visible transformation\n\n"
    "We’ll be right here whenever you’re ready to start your journey. 🌿"
)


async def send_follow_up2(db: Session, *, wa_id: str, from_wa_id: str = "917729992376") -> Dict[str, Any]:
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
        "type": "text",
        "text": {"body": FOLLOW_UP_2_TEXT},
    }

    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send follow-up 2: {res.text}")

    message_id = res.json().get("messages", [{}])[0].get("id")

    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    message_data = MessageCreate(
        message_id=message_id or f"outbound_{datetime.utcnow().timestamp()}",
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="text",
        body=FOLLOW_UP_2_TEXT,
        timestamp=datetime.utcnow(),
        customer_id=customer.id,
    )
    message_service.create_message(db, message_data)

    return {"success": True, "message_id": message_id}


async def schedule_follow_up2_after_follow_up1(wa_id: str, fu1_sent_at: datetime) -> None:
    """Wait 30 minutes after Follow-Up 1, then send Follow-Up 2 if no reply since FU1."""
    try:
        await asyncio.sleep(FOLLOW_UP_2_DELAY_MINUTES * 60)

        db: Optional[Session] = None
        try:
            db = SessionLocal()

            # Ensure user remains in lead appointment flow
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                state = (lead_appointment_state.get(wa_id) or {})
                if state.get("flow_context") != "lead_appointment":
                    return
            except Exception:
                return

            cust = customer_service.get_customer_record_by_wa_id(db, wa_id)
            if not cust:
                return

            # If user interacted after FU1, skip
            if cust.last_interaction_time and cust.last_interaction_time > fu1_sent_at:
                return

            await send_follow_up2(db, wa_id=wa_id)

        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass
    except Exception:
        return


