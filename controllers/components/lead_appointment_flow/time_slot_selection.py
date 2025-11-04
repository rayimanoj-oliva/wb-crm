"""
Time Slot Selection for Lead-to-Appointment Booking Flow
Handles time slot selection using existing slot system
"""

from datetime import datetime, timedelta
from typing import Dict, Any
import os
import requests

from sqlalchemy.orm import Session
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def send_time_slot_selection(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send week selection for lead appointment flow.
    
    This function is used within the lead appointment flow context after clinic selection.
    """
    
    try:
        # Use LEAD APPOINTMENT specific week list functionality
        from controllers.components.interactive_type import send_lead_week_list
        result = await send_lead_week_list(db, wa_id)
        # Arm Follow-Up 1 after this outbound prompt in case user stops here
        try:
            import asyncio
            from .follow_up1 import schedule_follow_up1_after_welcome
            asyncio.create_task(schedule_follow_up1_after_welcome(wa_id, datetime.utcnow()))
        except Exception:
            pass
        return {"success": result.get("success", False), "result": result}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending week options: {str(e)}", db)
        return {"success": False, "error": str(e)}


# Removed handle_time_slot_selection and handle_custom_date_input functions
# Now using existing week/date/slot logic directly from interactive_type.py
