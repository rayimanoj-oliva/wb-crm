"""
Auto Welcome Message for Lead-to-Appointment Booking Flow
Sends the initial welcome message with Yes/No buttons
"""

from datetime import datetime
from typing import Dict, Any
import os
import requests

from sqlalchemy.orm import Session
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def send_auto_welcome_message(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send the auto-welcome message with Yes/No buttons for appointment booking.
    
    Returns a status dict.
    """
    
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send welcome message right now.", db)
            return {"success": False, "error": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": "Thank you for your interest in Oliva Skin & Hair Clinic — India's most trusted dermatology chain. 🌿\n\nWe're happy to assist you! Would you like to book an appointment with us today?"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "yes_book_appointment", "title": "Yes, Book Now"}},
                        {"type": "reply", "reply": {"id": "not_now", "title": "Not Now"}},
                    ]
                },
            },
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        if resp.status_code == 200:
            try:
                # Get message ID from response
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                
                # Get or create customer
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate
                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                
                # Save outbound message to database
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Thank you for your interest in Oliva Skin & Hair Clinic — India's most trusted dermatology chain. 🌿\n\nWe're happy to assist you! Would you like to book an appointment with us today?",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Auto welcome message saved to database: {message_id}")
                
                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Thank you for your interest in Oliva Skin & Hair Clinic — India's most trusted dermatology chain. 🌿\n\nWe're happy to assist you! Would you like to book an appointment with us today?",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "buttons",
                        "options": ["✅ Yes, I'd like to book", "❌ Not now"]
                    }
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"success": True, "message_id": message_id}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send welcome message. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending welcome message: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_welcome_response(
    db: Session, 
    *, 
    wa_id: str, 
    reply_id: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle the response to the auto-welcome message.
    
    Args:
        reply_id: Either "yes_book_appointment" or "not_now"
        
    Returns a status dict.
    """
    
    normalized_reply = (reply_id or "").strip().lower()
    
    if normalized_reply == "yes_book_appointment":
        # User wants to book - initialize flow state and proceed to city selection
        try:
            from controllers.web_socket import lead_appointment_state
            if wa_id not in lead_appointment_state:
                lead_appointment_state[wa_id] = {}
            print(f"[lead_appointment_flow] DEBUG - Initialized lead appointment state for {wa_id}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not initialize lead appointment state: {e}")
        
        from .city_selection import send_city_selection
        result = await send_city_selection(db, wa_id=wa_id)
        return {"status": "proceed_to_city_selection", "result": result}
    
    elif normalized_reply == "not_now":
        # User doesn't want to book now - still create a lead but mark as no callback
        from .zoho_integration import trigger_zoho_lead_creation
        try:
            await trigger_zoho_lead_creation(
                db=db,
                wa_id=wa_id,
                customer=customer,
                lead_status="NO_CALLBACK",
                appointment_preference="Not interested now"
            )
            await send_message_to_waid(
                wa_id, 
                "No problem! We've saved your details. Feel free to reach out anytime when you're ready to book an appointment. 😊", 
                db
            )
            return {"status": "lead_created_no_callback"}
        except Exception as e:
            print(f"[lead_appointment_flow] ERROR - Failed to create lead for 'not now': {e}")
            await send_message_to_waid(
                wa_id, 
                "Thank you for your interest! Feel free to reach out anytime. 😊", 
                db
            )
            return {"status": "acknowledged"}
    
    return {"status": "skipped"}
