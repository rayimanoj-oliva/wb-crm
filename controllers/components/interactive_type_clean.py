from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import os
import re
import json
import requests
from sqlalchemy.orm import Session

from config.constants import get_messages_url
from services import message_service, order_service
from services.whatsapp_service import get_latest_token
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def run_interactive_type(
    db: Session,
    *,
    message: Dict[str, Any],
    interactive: Dict[str, Any],
    i_type: str,
    timestamp: datetime,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    wa_id: str,
    customer: Any,
) -> Dict[str, Any]:
    """Handle WhatsApp interactive payloads (button_reply, list_reply).

    Returns a status dict. If not handled, returns {"status": "skipped"}.
    """

    # Flow handling removed - flows are disabled
    if i_type == "flow":
        return {"status": "flow_disabled", "message_id": message_id}

    # 1) Persist button/list replies early and delegate treatment buttons to existing flow
    try:
        if i_type in {"button_reply", "list_reply"}:
            title = interactive.get("button_reply", {}).get("title") if i_type == "button_reply" else interactive.get("list_reply", {}).get("title")
            reply_id = interactive.get("button_reply", {}).get("id") if i_type == "button_reply" else interactive.get("list_reply", {}).get("id")
            
            # Save interactive message to database
            reply_text = title or reply_id or "[Interactive Reply]"
            msg_interactive = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="interactive",
                body=reply_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, msg_interactive)
            db.commit()  # Explicitly commit the transaction
            
            # Broadcast to WebSocket
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "interactive",
                "message": reply_text,
                "timestamp": timestamp.isoformat(),
            })
            
            # Mark customer as replied and reset follow-up timer for ANY interactive response
            # This ensures follow-up timer resets from user's last interaction
            try:
                from services.followup_service import mark_customer_replied as _mark_replied
                _mark_replied(db, customer_id=customer.id, reset_followup_timer=True)
                print(f"[interactive_type_clean] DEBUG - Customer {wa_id} interactive reply ({i_type}: {reply_id}) - reset follow-up timer")
            except Exception as e:
                print(f"[interactive_type_clean] WARNING - Could not mark customer replied for interactive: {e}")

            # Delegate Skin/Hair/Body and related list selections to component flow
            from controllers.components.treament_flow import run_treatment_buttons_flow  # local import to avoid cycles
            flow_result = await run_treatment_buttons_flow(
                db,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                message_id=message_id,
                btn_id=reply_id,
                btn_text=title,
            )
            if (flow_result or {}).get("status") in {"list_sent", "hair_template_sent", "body_template_sent", "next_actions_sent"}:
                return flow_result

            # Delegate appointment buttons (book, callback, time)
            from controllers.components.treament_flow import run_appointment_buttons_flow  # type: ignore
            appt_result = await run_appointment_buttons_flow(
                db,
                wa_id=wa_id,
                btn_id=reply_id,
                btn_text=title,
            )
            if (appt_result or {}).get("status") in {"date_list_sent", "callback_ack", "appointment_captured", "need_date_first"}:
                return appt_result
    except Exception:
        pass

    return {"status": "skipped"}


def _format_week_label(start: datetime, end: datetime) -> str:
    try:
        # Examples: "Oct 14–20", "Oct 28–Nov 3"
        start_str = start.strftime("%b %d")
        end_str = end.strftime("%b %d")
        if start.month == end.month:
            return f"{start.strftime('%b')} {start.day}–{end.day}"
        else:
            return f"{start_str}–{end_str}"
    except Exception:
        return "Week"


def _generate_week_rows() -> list:
    """Generate week selection rows for the next 4 weeks."""
    try:
        from datetime import datetime, timedelta
        
        rows = []
        today = datetime.now()
        
        for i in range(4):
            week_start = today + timedelta(days=7*i)
            week_end = week_start + timedelta(days=6)
            
            label = _format_week_label(week_start, week_end)
            week_id = f"week_{week_start.strftime('%Y%m%d')}"
            
            rows.append({
                "id": week_id,
                "title": label,
                "description": f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
            })
        
        return rows
    except Exception:
        return []


def _generate_time_rows_for_slot(slot_id: str) -> list:
    """Generate time selection rows for a specific slot."""
    try:
        if slot_id == "slot_morning":
            times = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
        elif slot_id == "slot_afternoon":
            times = ["14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]
        elif slot_id == "slot_evening":
            times = ["18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
        else:
            return []
        
        rows = []
        for time in times:
            rows.append({
                "id": f"time_{time}",
                "title": time,
                "description": f"Book at {time}"
            })
        
        return rows
    except Exception:
        return []
