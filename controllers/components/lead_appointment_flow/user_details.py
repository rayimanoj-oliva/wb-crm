"""
User Details Collection for Lead-to-Appointment Booking Flow
Collects name and phone number before callback confirmation
"""

from datetime import datetime
from typing import Dict, Any
import re

from sqlalchemy.orm import Session
from utils.whatsapp import send_message_to_waid


async def send_user_details_request(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send request for user details (name and phone number).
    
    Returns a status dict.
    """
    
    try:
        await send_message_to_waid(
            wa_id, 
            "📝 To complete your appointment booking, please provide your details:\n\n"
            "Please send your name and phone number in this format:\n"
            "Name: [Your Full Name]\n"
            "Phone: [Your 10-digit phone number]\n\n"
            "Example:\n"
            "Name: John Smith\n"
            "Phone: 9876543210",
            db
        )
        
        # Set flag that we're waiting for user details
        try:
            from controllers.web_socket import lead_appointment_state
            if wa_id not in lead_appointment_state:
                lead_appointment_state[wa_id] = {}
            lead_appointment_state[wa_id]["waiting_for_user_details"] = True
            print(f"[lead_appointment_flow] DEBUG - Set waiting for user details")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not set user details flag: {e}")
        
        return {"success": True, "status": "waiting_for_user_details"}
        
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error requesting details: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_user_details_input(
    db: Session, 
    *, 
    wa_id: str, 
    details_text: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle user details input from user.
    
    Args:
        details_text: Text containing name and phone number
        
    Returns a status dict.
    """
    
    try:
        # Parse the details text
        name = None
        phone = None
        
        # Extract name
        name_match = re.search(r'Name:\s*(.+)', details_text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
        
        # Extract phone
        phone_match = re.search(r'Phone:\s*(\d{10})', details_text, re.IGNORECASE)
        if phone_match:
            phone = phone_match.group(1).strip()
        
        # If format not followed, try to extract from plain text
        if not name or not phone:
            lines = details_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not name and len(line) > 2 and not line.isdigit():
                    name = line
                elif not phone and line.isdigit() and len(line) == 10:
                    phone = line
        
        # Validate the extracted information
        if not name or len(name) < 2:
            await send_message_to_waid(
                wa_id, 
                "❌ Please provide a valid name (at least 2 characters).\n\n"
                "Please send your details in this format:\n"
                "Name: [Your Full Name]\n"
                "Phone: [Your 10-digit phone number]",
                db
            )
            return {"status": "invalid_name"}
        
        if not phone or not phone.isdigit() or len(phone) != 10:
            await send_message_to_waid(
                wa_id, 
                "❌ Please provide a valid 10-digit phone number.\n\n"
                "Please send your details in this format:\n"
                "Name: [Your Full Name]\n"
                "Phone: [Your 10-digit phone number]",
                db
            )
            return {"status": "invalid_phone"}
        
        # Store the user details
        try:
            from controllers.web_socket import lead_appointment_state
            if wa_id not in lead_appointment_state:
                lead_appointment_state[wa_id] = {}
            lead_appointment_state[wa_id]["user_name"] = name
            lead_appointment_state[wa_id]["user_phone"] = phone
            lead_appointment_state[wa_id]["waiting_for_user_details"] = False
            print(f"[lead_appointment_flow] DEBUG - Stored user details: {name}, {phone}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not store user details: {e}")
        
        # Update customer record with the details
        try:
            from services.customer_service import update_customer
            from schemas.customer_schema import CustomerUpdate
            
            customer_update = CustomerUpdate(
                name=name,
                phone=phone
            )
            updated_customer = update_customer(db, customer.id, customer_update)
            print(f"[lead_appointment_flow] DEBUG - Updated customer record: {updated_customer.name}, {updated_customer.phone}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not update customer record: {e}")
        
        # Send confirmation and proceed to callback confirmation
        await send_message_to_waid(
            wa_id, 
            f"✅ Thank you {name}! Your details have been saved.\n\n"
            f"📞 Phone: {phone}\n"
            f"📧 WhatsApp: {wa_id}\n\n"
            "Now, would you like one of our agents to call you back to confirm your appointment?",
            db
        )
        
        # Proceed to callback confirmation
        from .callback_confirmation import send_callback_confirmation
        result = await send_callback_confirmation(db=db, wa_id=wa_id)
        return {"status": "callback_confirmation_sent", "user_name": name, "user_phone": phone, "result": result}
            
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Failed to handle user details: {e}")
        await send_message_to_waid(wa_id, "❌ Error processing your details. Please try again.", db)
        return {"status": "error"}


async def send_callback_confirmation(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send callback confirmation message.
    
    Returns a status dict.
    """
    
    try:
        from utils.whatsapp import send_message_to_waid
        import os
        import requests
        from services.whatsapp_service import get_latest_token
        from config.constants import get_messages_url
        
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
            }
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
                from utils.ws_manager import manager
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Would you like one of our agents to call you back to confirm your appointment?",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "button",
                        "buttons": ["Yes, Call Me", "No, Keep Details"]
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
