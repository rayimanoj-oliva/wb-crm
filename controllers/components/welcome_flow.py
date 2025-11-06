from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import os
import re
import requests
from sqlalchemy.orm import Session

from services.whatsapp_service import get_latest_token
from services import message_service
from schemas.message_schema import MessageCreate
from config.constants import get_messages_url
from utils.ws_manager import manager
from controllers.components.products_flow import run_buy_products_flow


async def run_welcome_flow(
    db: Session,
    *,
    message_type: str,
    body_text: str,
    wa_id: str,
    to_wa_id: str,
    sender_name: Optional[str],
    customer: Any,
) -> Dict[str, Any]:
    """Send welcome template on greetings like Hi/Hello/Hlo.

    Returns {"status": "sent"|"skipped"|"failed", ...}.
    """

    # As requested: do not send welcome_msg template for any text.
    return {"status": "skipped"}

    token_entry = get_latest_token(db)
    if not (token_entry and token_entry.token):
        return {"status": "failed", "reason": "no_token"}

    try:
        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        media_id = os.getenv("WELCOME_TEMPLATE_MEDIA_ID") or "2332791820506535"
        if not media_id:
            try:
                user_prior_messages = message_service.get_messages_by_wa_id(db, wa_id)
                last_images = [m for m in reversed(user_prior_messages) if m.type == "image" and m.media_id]
                if last_images:
                    media_id = last_images[0].media_id
            except Exception:
                media_id = None

        components = []
        if media_id:
            components.append({
                "type": "header",
                "parameters": [{"type": "image", "image": {"id": media_id}}]
            })
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": sender_name}]
        })

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "template",
            "template": {
                "name": "welcome_msg",
                "language": {"code": "en_US"},
                **({"components": components} if components else {})
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code != 200:
            return {"status": "failed", "status_code": resp.status_code, "error": resp.text[:500]}

        try:
            tpl_msg_id = resp.json()["messages"][0]["id"]
            tpl_message = MessageCreate(
                message_id=tpl_msg_id,
                from_wa_id=to_wa_id,
                to_wa_id=wa_id,
                type="template",
                body=f"Welcome template sent to {sender_name}",
                timestamp=datetime.now(),
                customer_id=customer.id,
                media_id=media_id if media_id else None,
            )
            message_service.create_message(db, tpl_message)
            try:
                await manager.broadcast({
                    "from": to_wa_id,
                    "to": wa_id,
                    "type": "template",
                    "message": f"Welcome template sent to {sender_name}",
                    "timestamp": datetime.now().isoformat(),
                    **({"media_id": media_id} if media_id else {}),
                })
            except Exception:
                pass
        except Exception:
            pass

        return {"status": "sent"}
    except Exception as e:
        return {"status": "failed", "reason": str(e)[:200]}



async def trigger_buy_products_from_welcome(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Helper to trigger the Buy Products catalogue flow from the welcome flow context."""
    return await run_buy_products_flow(db, wa_id=wa_id)
