"""
Clinic Location Selection for Lead-to-Appointment Booking Flow
Handles clinic location selection based on selected city
"""

from datetime import datetime
from typing import Dict, Any, List
import os
import requests

from sqlalchemy.orm import Session
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


def get_clinics_for_city(city: str) -> List[Dict[str, str]]:
    """Get list of clinics for a given city.
    
    Returns a list of clinic dictionaries with id and title.
    """
    
    # Static mapping of cities to clinics
    # In a real implementation, this could be fetched from a database
    clinics_mapping = {
        "Hyderabad": [
            {"id": "clinic_hyderabad_banjara", "title": "Banjara Hills"},
            {"id": "clinic_hyderabad_jubilee", "title": "Jubilee Hills"},
            {"id": "clinic_hyderabad_hitec", "title": "HITEC City"},
            {"id": "clinic_hyderabad_secunderabad", "title": "Secunderabad"},
        ],
        "Bengaluru": [
            {"id": "clinic_bengaluru_koramangala", "title": "Koramangala"},
            {"id": "clinic_bengaluru_indiranagar", "title": "Indiranagar"},
            {"id": "clinic_bengaluru_whitefield", "title": "Whitefield"},
            {"id": "clinic_bengaluru_jayanagar", "title": "Jayanagar"},
        ],
        "Chennai": [
            {"id": "clinic_chennai_tnagar", "title": "T. Nagar"},
            {"id": "clinic_chennai_adyar", "title": "Adyar"},
            {"id": "clinic_chennai_anna_nagar", "title": "Anna Nagar"},
            {"id": "clinic_chennai_velachery", "title": "Velachery"},
        ],
        "Pune": [
            {"id": "clinic_pune_koregaon", "title": "Koregaon Park"},
            {"id": "clinic_pune_baner", "title": "Baner"},
            {"id": "clinic_pune_hadapsar", "title": "Hadapsar"},
            {"id": "clinic_pune_viman_nagar", "title": "Viman Nagar"},
        ],
        "Kochi": [
            {"id": "clinic_kochi_kaloor", "title": "Kaloor"},
            {"id": "clinic_kochi_kakkanad", "title": "Kakkanad"},
            {"id": "clinic_kochi_edapally", "title": "Edapally"},
        ],
        "Other": [
            {"id": "clinic_other_consultation", "title": "Online Consultation"},
            {"id": "clinic_other_callback", "title": "Call Back Required"},
        ]
    }
    
    return clinics_mapping.get(city, [])


async def send_clinic_location(db: Session, *, wa_id: str, city: str) -> Dict[str, Any]:
    """Send clinic location selection based on the selected city.
    
    Returns a status dict.
    """
    
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send clinic options right now.", db)
            return {"success": False, "error": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        clinics = get_clinics_for_city(city)
        
        if not clinics:
            await send_message_to_waid(wa_id, f"❌ No clinics available in {city}. Please select a different city.", db)
            return {"success": False, "error": "no_clinics"}

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": f"Great! Please choose your preferred clinic location in {city}."},
                "action": {
                    "button": "Choose Clinic",
                    "sections": [
                        {
                            "title": f"{city} Clinics",
                            "rows": clinics
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
                    body=f"Great! Please choose your preferred clinic location in {city}.",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Clinic location message saved to database: {message_id}")
                
                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": f"Great! Please choose your preferred clinic location in {city}.",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "list",
                        "section": f"{city} Clinics"
                    }
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"success": True, "message_id": message_id}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send clinic options. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending clinic options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_clinic_location(
    db: Session, 
    *, 
    wa_id: str, 
    reply_id: str, 
    customer: Any
) -> Dict[str, Any]:
    """Handle clinic location selection response.
    
    Args:
        reply_id: Clinic ID like "clinic_hyderabad_banjara", etc.
        
    Returns a status dict.
    """
    
    # Extract clinic name from ID
    clinic_name = "Unknown Clinic"
    try:
        # Parse clinic ID to get readable name
        parts = (reply_id or "").split("_")
        if len(parts) >= 3:
            clinic_name = " ".join(parts[2:]).title()
        else:
            clinic_name = reply_id.replace("clinic_", "").replace("_", " ").title()
    except Exception:
        clinic_name = reply_id or "Unknown Clinic"
    
    # Store selected clinic in session
    try:
        from controllers.web_socket import lead_appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        lead_appointment_state[wa_id]["selected_clinic"] = clinic_name
        lead_appointment_state[wa_id]["clinic_id"] = reply_id
        print(f"[lead_appointment_flow] DEBUG - Stored clinic selection: {clinic_name}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not store clinic selection: {e}")
    
    # Send confirmation and proceed to time slot selection
    await send_message_to_waid(wa_id, f"✅ Perfect! You selected {clinic_name}.", db)
    
    # Proceed to time slot selection
    from .time_slot_selection import send_time_slot_selection
    result = await send_time_slot_selection(db, wa_id=wa_id)
    
    return {"status": "proceed_to_time_slot", "clinic": clinic_name, "result": result}
