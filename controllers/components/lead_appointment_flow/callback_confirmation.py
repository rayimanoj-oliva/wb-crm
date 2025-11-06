"""
Callback Confirmation for Lead-to-Appointment Booking Flow
Handles callback confirmation with Zoho Auto-Dial and Lead creation triggers
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


async def send_callback_confirmation(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send callback confirmation with Yes/No buttons.
    
    Returns a status dict.
    """
    
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send callback options right now.", db)
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
                    "text": "Would you like one of our agents to call you back to confirm your appointment?"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "yes_callback", "title": "Yes, Call Me"}},
                        {"type": "reply", "reply": {"id": "no_callback", "title": "No, Keep Details"}},
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
                    body="Would you like one of our agents to call you back to confirm your appointment?",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Callback confirmation message saved to database: {message_id}")
                
                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Would you like one of our agents to call you back to confirm your appointment?",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "buttons",
                        "options": ["📞 Yes, please call me", "💬 No, just keep my details"]
                    }
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"success": True, "message_id": message_id}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send callback options. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending callback options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_callback_confirmation(
    db: Session, 
    *, 
    wa_id: str, 
    reply_id: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle callback confirmation response.
    
    Args:
        reply_id: Either "yes_callback" or "no_callback"
        
    Returns a status dict.
    """
    
    normalized_reply = (reply_id or "").strip().lower()
    
    # Get appointment details from session
    appointment_details = {}
    try:
        from controllers.web_socket import lead_appointment_state
        appointment_details = lead_appointment_state.get(wa_id, {})
        print(f"[lead_appointment_flow] DEBUG - Appointment details: {appointment_details}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not get appointment details: {e}")
    
    if normalized_reply == "yes_callback":
        # User wants callback - trigger Q5 auto-dial event
        try:
            from .zoho_lead_service import trigger_q5_auto_dial_event
            
            # Trigger Q5 auto-dial event (creates lead + triggers auto-dial)
            q5_result = await trigger_q5_auto_dial_event(
                db=db,
                wa_id=wa_id,
                customer=customer,
                appointment_details=appointment_details
            )
            
            await send_message_to_waid(
                wa_id, 
                "✅ Perfect! We've noted your appointment details and one of our agents will call you shortly to confirm your appointment. Thank you! 😊", 
                db
            )
            
            # Clear session data
            try:
                from controllers.web_socket import lead_appointment_state
                if wa_id in lead_appointment_state:
                    del lead_appointment_state[wa_id]
                # Also clear appointment_state flags to allow new flow start
                from controllers.web_socket import appointment_state
                if wa_id in appointment_state:
                    appointment_state[wa_id].pop("mr_welcome_sent", None)
                    appointment_state[wa_id].pop("mr_welcome_sending_ts", None)
                print(f"[lead_appointment_flow] DEBUG - Cleared appointment session data")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Could not clear session data: {e}")
            
            return {
                "status": "callback_initiated", 
                "q5_result": q5_result
            }
            
        except Exception as e:
            print(f"[lead_appointment_flow] ERROR - Failed to trigger callback: {e}")
            await send_message_to_waid(
                wa_id, 
                "✅ We've noted your appointment details. Our team will contact you soon. Thank you! 😊", 
                db
            )
            return {"status": "callback_fallback"}
    
    elif normalized_reply == "no_callback":
        # User doesn't want callback - create lead for follow-up/remarketing
        try:
            from .zoho_lead_service import handle_termination_event
            
            termination_result = await handle_termination_event(
                db=db,
                wa_id=wa_id,
                customer=customer,
                termination_reason="negative_q5_response",
                appointment_details=appointment_details
            )
            
            await send_message_to_waid(
                wa_id, 
                "✅ Thank you! We've saved your appointment details. You can reach out to us anytime if you need any assistance. 😊", 
                db
            )
            
            # Clear session data
            try:
                from controllers.web_socket import lead_appointment_state
                if wa_id in lead_appointment_state:
                    del lead_appointment_state[wa_id]
                # Also clear appointment_state flags to allow new flow start
                from controllers.web_socket import appointment_state
                if wa_id in appointment_state:
                    appointment_state[wa_id].pop("mr_welcome_sent", None)
                    appointment_state[wa_id].pop("mr_welcome_sending_ts", None)
                print(f"[lead_appointment_flow] DEBUG - Cleared appointment session data")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Could not clear session data: {e}")
            
            return {"status": "lead_created_no_callback", "termination_result": termination_result}
            
        except Exception as e:
            print(f"[lead_appointment_flow] ERROR - Failed to create lead: {e}")
            await send_message_to_waid(
                wa_id, 
                "✅ Thank you for your interest! We've noted your details. 😊", 
                db
            )
            return {"status": "lead_fallback"}
    
    else:
        await send_message_to_waid(wa_id, "❌ Invalid selection. Please try again.", db)
        return {"status": "invalid_selection"}
