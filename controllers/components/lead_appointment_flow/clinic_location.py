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
from .config import LEAD_APPOINTMENT_PHONE_ID, LEAD_APPOINTMENT_DISPLAY_LAST10


def get_clinics_for_city(city: str) -> List[Dict[str, str]]:
    """Get list of clinics for a given city.
    
    Returns a list of clinic dictionaries with id and title.
    """
    
    # Static mapping of cities to clinics
    # In a real implementation, this could be fetched from a database
    clinics_mapping = {
    "Ahmedabad": [ 
        {"id": "clinic_ahmedabad_cgroad", "title": "CG Road"},
    ],

    "Bangalore": [
        {"id": "clinic_bangalore_electroniccity", "title": "Electronic City"},
        {"id": "clinic_bangalore_hrbr", "title": "HRBR Layout"},
        {"id": "clinic_bangalore_hsr", "title": "HSR Layout"},
        {"id": "clinic_bangalore_indiranagar", "title": "Indira Nagar"},
        {"id": "clinic_bangalore_jayanagar", "title": "Jayanagar"},
        {"id": "clinic_bangalore_koramangala", "title": "Koramangala"},
        {"id": "clinic_bangalore_sadashivanagar", "title": "Sadashiva Nagar"},
        {"id": "clinic_bangalore_whitefield", "title": "Whitefield"},
        {"id": "clinic_bangalore_yelahanka", "title": "Yelahanka"},
    ],

    "Chennai": [
        {"id": "clinic_chennai_adyar", "title": "Adyar"},
        {"id": "clinic_chennai_alwarpet", "title": "Alwarpet"},
        {"id": "clinic_chennai_annanagar", "title": "Anna Nagar"},
        {"id": "clinic_chennai_sholinganallur", "title": "Sholinganallur"},
    ],

    "Hyderabad": [
        {"id": "clinic_hyderabad_banjara", "title": "Banjara Hills"},
        {"id": "clinic_hyderabad_dilsukhnagar", "title": "Dilsukhnagar"},
        {"id": "clinic_hyderabad_gachibowli", "title": "Gachibowli"},
        {"id": "clinic_hyderabad_himayatnagar", "title": "Himayatnagar"},
        {"id": "clinic_hyderabad_jubilee", "title": "Jubilee Hills"},
        {"id": "clinic_hyderabad_kokapet", "title": "Kokapet"},
        {"id": "clinic_hyderabad_kukatpally", "title": "Kukatpally"},
        {"id": "clinic_hyderabad_secunderabad", "title": "Secunderabad"},
    ],

    "Kochi": [
        {"id": "clinic_kochi_kadavanthra", "title": "Kadavanthra"},
    ],

    "Kolkata": [
        {"id": "clinic_kolkata_jodhpurpark", "title": "Jodhpur Park"},
        {"id": "clinic_kolkata_parkstreet", "title": "Park Street"},
        {"id": "clinic_kolkata_saltlake", "title": "Salt Lake"},
    ],

    "Ludhiana": [
        {"id": "clinic_ludhiana_sarabhanagar", "title": "Sarabha Nagar"},
    ],

    "Pune": [
        {"id": "clinic_pune_aundh", "title": "Aundh"},
        {"id": "clinic_pune_kalyaninagar", "title": "Kalyani Nagar"},
        {"id": "clinic_pune_kharadi", "title": "Kharadi"},
        {"id": "clinic_pune_shivajinagar", "title": "Shivaji Nagar"},
    ],

    "Vijayawada": [
        {"id": "clinic_vijayawada_gurunanakcolony", "title": "Guru Nanak Colony Road"},
    ],

    "Vizag": [
        {"id": "clinic_vizag_dwarakanagar", "title": "Dwaraka Nagar"},
    ],

    "Other": [
        {"id": "clinic_other_consultation", "title": "Online Consultation"},
        {"id": "clinic_other_callback", "title": "Call Back Required"},
    ],
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
        phone_id = str(LEAD_APPOINTMENT_PHONE_ID)

        # Use city directly (no normalization - keep Bangalore as Bangalore)
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
            message_id = f"outbound_{datetime.now().timestamp()}"
            try:
                # Get message ID from response
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", message_id)
                
                # Get or create customer
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate
                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                
                # Save outbound message to database
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=("91" + LEAD_APPOINTMENT_DISPLAY_LAST10),
                    to_wa_id=wa_id,
                    type="interactive",
                    body=f"Great! Please choose your preferred clinic location in {city}.",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Clinic location message saved to database: {message_id}")
                
                # Mark clinic location as sent for idempotency
                try:
                    from controllers.web_socket import lead_appointment_state
                    if wa_id not in lead_appointment_state:
                        lead_appointment_state[wa_id] = {}
                    lead_appointment_state[wa_id]["clinic_location_sent"] = True
                    lead_appointment_state[wa_id]["clinic_location_sent_ts"] = datetime.now().isoformat()
                except Exception:
                    pass
                
                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": ("91" + LEAD_APPOINTMENT_DISPLAY_LAST10),
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
            # Arm Follow-Up 1 after this outbound prompt in case user stops here
            try:
                import asyncio
                from .follow_up1 import schedule_follow_up1_after_welcome
                asyncio.create_task(schedule_follow_up1_after_welcome(wa_id, datetime.utcnow()))
            except Exception:
                pass
            
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
    
    # Store selected clinic in session (also mirror to selected_location for Zoho Clinic_Branch)
    try:
        from controllers.web_socket import lead_appointment_state, appointment_state
        if wa_id not in lead_appointment_state:
            lead_appointment_state[wa_id] = {}
        lead_appointment_state[wa_id]["selected_clinic"] = clinic_name
        lead_appointment_state[wa_id]["clinic_id"] = reply_id
        # For Zoho picklist mapping
        lead_appointment_state[wa_id]["selected_location"] = clinic_name
        # Also persist in appointment_state as a fallback source
        st = appointment_state.get(wa_id) or {}
        st["selected_location"] = clinic_name
        # Mirror selected clinic for clarity
        st["selected_clinic"] = clinic_name
        appointment_state[wa_id] = st
        print(f"[lead_appointment_flow] DEBUG - Stored clinic selection: {clinic_name}")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not store clinic selection: {e}")
    
    # Send confirmation and proceed to time slot selection
    await send_message_to_waid(wa_id, f"✅ Perfect! You selected {clinic_name}.", db)
    
    # Log last step reached: treatment (clinic selected, treatment/concern is used here)
    try:
        from utils.flow_log import log_last_step_reached
        log_last_step_reached(
            db,
            flow_type="lead_appointment",
            step="treatment",
            wa_id=wa_id,
            name=(getattr(customer, "name", None) or "") if customer else None,
        )
        print(f"[lead_appointment_flow] ✅ Logged last step: treatment")
    except Exception as e:
        print(f"[lead_appointment_flow] WARNING - Could not log last step: {e}")
    
    # Proceed to time slot selection
    from .time_slot_selection import send_time_slot_selection
    result = await send_time_slot_selection(db, wa_id=wa_id)
    
    return {"status": "proceed_to_time_slot", "clinic": clinic_name, "result": result}
