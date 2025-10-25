"""
City Selection for Lead-to-Appointment Booking Flow
Handles city selection with quick replies
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


async def send_city_selection(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send city selection with quick replies.
    
    Returns a status dict.
    """
    
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send city options right now.", db)
            return {"success": False, "error": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "Please select your city from the list below 👇"},
                "action": {
                    "button": "Choose City",
                    "sections": [
                        {
                            "title": "Available Cities",
                            "rows": [
                                {"id": "city_hyderabad", "title": "Hyderabad"},
                                {"id": "city_bengaluru", "title": "Bengaluru"},
                                {"id": "city_chennai", "title": "Chennai"},
                                {"id": "city_pune", "title": "Pune"},
                                {"id": "city_kochi", "title": "Kochi"},
                                {"id": "city_other", "title": "Other"},
                            ]
                        }
                    ]
                }
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
                    body="Please select your city from the list below 👇",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - City selection message saved to database: {message_id}")
                
                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Please select your city from the list below 👇",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "list",
                        "section": "Available Cities"
                    }
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"success": True, "message_id": message_id}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send city options. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending city options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_city_selection(
    db: Session, 
    *, 
    wa_id: str, 
    reply_id: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle city selection response.
    
    Args:
        reply_id: City ID like "city_hyderabad", "city_bengaluru", etc.
        
    Returns a status dict.
    """
    
    # Map city IDs to city names
    city_mapping = {
        "city_hyderabad": "Hyderabad",
        "city_bengaluru": "Bengaluru", 
        "city_chennai": "Chennai",
        "city_pune": "Pune",
        "city_kochi": "Kochi",
        "city_other": "Other"
    }
    
    normalized_reply = (reply_id or "").strip().lower()
    selected_city = city_mapping.get(normalized_reply)
    
    if not selected_city:
        await send_message_to_waid(wa_id, "❌ Invalid city selection. Please try again.", db)
        return {"status": "invalid_selection"}
    
    # Store selected city in customer data or session
    try:
        from controllers.web_socket import lead_appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        lead_appointment_state[wa_id]["selected_city"] = selected_city
        print(f"[lead_appointment_flow] DEBUG - Stored city selection: {selected_city}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not store city selection: {e}")
    
    # Send confirmation and proceed to clinic location
    await send_message_to_waid(wa_id, f"✅ Great! You selected {selected_city}.", db)
    
    # Proceed to clinic location selection
    from .clinic_location import send_clinic_location
    result = await send_clinic_location(db, wa_id=wa_id, city=selected_city)
    
    return {"status": "proceed_to_clinic_location", "city": selected_city, "result": result}
