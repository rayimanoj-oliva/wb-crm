"""
Zoho CRM Integration for Lead-to-Appointment Booking Flow
Handles Zoho Auto-Dial and Lead creation APIs
"""

from datetime import datetime
from typing import Dict, Any, Optional
import requests
import json

from sqlalchemy.orm import Session
from utils.zoho_auth import get_valid_access_token
from utils.whatsapp import send_message_to_waid


async def trigger_zoho_auto_dial(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    appointment_details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Trigger Zoho Auto-Dial API for callback.
    
    Returns a status dict.
    """
    
    try:
        access_token = get_valid_access_token()
        if not access_token:
            print(f"[lead_appointment_flow] ERROR - No Zoho access token available")
            return {"success": False, "error": "no_access_token"}
        
        # Prepare auto-dial payload
        phone_number = wa_id.replace("+", "").replace(" ", "")
        if not phone_number.startswith("91"):
            phone_number = f"91{phone_number}"
        
        # Get appointment details for context
        city = appointment_details.get("selected_city", "Unknown")
        clinic = appointment_details.get("selected_clinic", "Unknown")
        appointment_date = appointment_details.get("custom_date", "Not specified")
        
        auto_dial_payload = {
            "phone_number": phone_number,
            "customer_name": getattr(customer, 'name', 'Customer'),
            "wa_id": wa_id,
            "appointment_city": city,
            "appointment_clinic": clinic,
            "appointment_date": appointment_date,
            "callback_reason": "Appointment Confirmation",
            "priority": "High",
            "source": "WhatsApp Lead-to-Appointment Flow"
        }
        
        # Make API call to Zoho Auto-Dial
        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json"
        }
        
        # Note: Replace with actual Zoho Auto-Dial API endpoint
        zoho_auto_dial_url = "https://www.zohoapis.in/crm/v2/functions/auto_dial/actions/execute"
        
        response = requests.post(
            zoho_auto_dial_url,
            headers=headers,
            json=auto_dial_payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print(f"[lead_appointment_flow] DEBUG - Auto-dial triggered successfully for {wa_id}")
            return {"success": True, "response": response.json()}
        else:
            print(f"[lead_appointment_flow] ERROR - Auto-dial failed: {response.status_code} - {response.text}")
            return {"success": False, "error": response.text}
            
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Auto-dial exception: {str(e)}")
        return {"success": False, "error": str(e)}


async def trigger_zoho_lead_creation(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    lead_status: str = "PENDING",
    appointment_details: Optional[Dict[str, Any]] = None,
    appointment_preference: Optional[str] = None
) -> Dict[str, Any]:
    """Create a lead in Zoho CRM.
    
    Args:
        lead_status: "PENDING", "CALL_INITIATED", or "NO_CALLBACK"
        appointment_details: Dictionary with appointment information
        appointment_preference: Additional preference text
        
    Returns a status dict.
    """
    
    try:
        print(f"[lead_appointment_flow] DEBUG - Starting lead creation for {wa_id}")
        print(f"[lead_appointment_flow] DEBUG - Lead status: {lead_status}")
        print(f"[lead_appointment_flow] DEBUG - Customer: {customer}")
        print(f"[lead_appointment_flow] DEBUG - Appointment details: {appointment_details}")
        
        access_token = get_valid_access_token()
        if not access_token:
            print(f"[lead_appointment_flow] ERROR - No Zoho access token available")
            return {"success": False, "error": "no_access_token"}
        
        print(f"[lead_appointment_flow] DEBUG - Access token obtained: {access_token[:20]}...")
        
        # Get user details from session state
        try:
            from controllers.web_socket import lead_appointment_state
            session_data = lead_appointment_state.get(wa_id, {})
            user_name = session_data.get("user_name", getattr(customer, 'name', 'Customer') or 'Customer')
            user_phone = session_data.get("user_phone", "")
            print(f"[lead_appointment_flow] DEBUG - User details from session: {user_name}, {user_phone}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not get user details from session: {e}")
            user_name = getattr(customer, 'name', 'Customer') or 'Customer'
            user_phone = ""
        
        # Prepare phone number - use user provided phone if available, otherwise use WA ID
        if user_phone and len(user_phone) == 10:
            phone_number = f"91{user_phone}"
            print(f"[lead_appointment_flow] DEBUG - Using user provided phone: {phone_number}")
        else:
            phone_number = wa_id.replace("+", "").replace(" ", "")
            if not phone_number.startswith("91"):
                phone_number = f"91{phone_number}"
            print(f"[lead_appointment_flow] DEBUG - Using WA ID as phone: {phone_number}")
        
        # Get appointment details from session state
        try:
            from controllers.web_socket import lead_appointment_state
            session_data = lead_appointment_state.get(wa_id, {})
            city = session_data.get("selected_city", "Unknown")
            clinic = session_data.get("selected_clinic", "Unknown")
            appointment_date = session_data.get("custom_date", "Not specified")
            print(f"[lead_appointment_flow] DEBUG - Appointment details from session: {city}, {clinic}, {appointment_date}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not get appointment details from session: {e}")
            city = appointment_details.get("selected_city", "Unknown") if appointment_details else "Unknown"
            clinic = appointment_details.get("selected_clinic", "Unknown") if appointment_details else "Unknown"
            appointment_date = appointment_details.get("custom_date", "Not specified") if appointment_details else "Not specified"
        
        # Create lead description
        description_parts = [
            f"Lead from WhatsApp Lead-to-Appointment Flow",
            f"City: {city}",
            f"Clinic: {clinic}",
            f"Preferred Date: {appointment_date}",
        ]
        
        if appointment_preference:
            description_parts.append(f"Preference: {appointment_preference}")
        
        description_parts.append(f"Status: {lead_status}")
        
        # Simplified lead data without custom fields to avoid API errors
        lead_data = {
            "data": [
                {
                    "First_Name": user_name,
                    "Last_Name": "",
                    "Phone": phone_number,
                    "Email": getattr(customer, 'email', '') or '',
                    "Lead_Source": "WhatsApp Lead-to-Appointment Flow",
                    "Lead_Status": lead_status,
                    "Company": "Oliva Skin & Hair Clinic",
                    "Description": " | ".join(description_parts),
                    "City": city,
                }
            ]
        }
        
        print(f"[lead_appointment_flow] DEBUG - Lead data prepared: {lead_data}")
        
        # Make API call to Zoho CRM
        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json"
        }
        
        zoho_leads_url = "https://www.zohoapis.in/crm/v2/Leads"
        
        print(f"[lead_appointment_flow] DEBUG - Making API call to: {zoho_leads_url}")
        response = requests.post(
            zoho_leads_url,
            headers=headers,
            json=lead_data,
            timeout=30
        )
        
        print(f"[lead_appointment_flow] DEBUG - API response status: {response.status_code}")
        print(f"[lead_appointment_flow] DEBUG - API response: {response.text}")
        
        if response.status_code in [200, 201]:
            response_data = response.json()
            lead_id = response_data.get("data", [{}])[0].get("details", {}).get("id")
            print(f"[lead_appointment_flow] DEBUG - Lead created successfully with ID: {lead_id}")
            
            # Log successful lead creation
            print(f"[zoho_integration] DEBUG - Lead created successfully: {wa_id}, Name: {user_name}, Lead ID: {lead_id}")
            
            return {"success": True, "lead_id": lead_id, "response": response_data}
        else:
            error_msg = f"API Error {response.status_code}: {response.text}"
            print(f"[lead_appointment_flow] ERROR - Lead creation failed: {error_msg}")
            
            # Log failed lead creation
            print(f"[zoho_integration] DEBUG - Lead creation failed: {wa_id}, Error: {error_msg}")
            
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        error_msg = f"Exception: {str(e)}"
        print(f"[lead_appointment_flow] ERROR - Lead creation exception: {error_msg}")
        import traceback
        print(f"[lead_appointment_flow] ERROR - Traceback: {traceback.format_exc()}")
        
        # Log exception
        print(f"[zoho_integration] DEBUG - Lead creation exception: {wa_id}, Error: {error_msg}")
        
        return {"success": False, "error": error_msg}


async def create_lead_for_dropoff(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    dropoff_point: str
) -> Dict[str, Any]:
    """Create a lead for users who drop off before completing the flow.
    
    Args:
        dropoff_point: Where the user dropped off (e.g., "city_selection", "clinic_selection", etc.)
        
    Returns a status dict.
    """
    
    try:
        # Get any partial appointment details
        appointment_details = {}
        try:
            from controllers.web_socket import lead_appointment_state
            appointment_details = lead_appointment_state.get(wa_id, {})
        except Exception:
            pass
        
        # Create lead with NO_CALLBACK status
        result = await trigger_zoho_lead_creation(
            db=db,
            wa_id=wa_id,
            customer=customer,
            lead_status="NO_CALLBACK",
            appointment_details=appointment_details,
            appointment_preference=f"Dropped off at: {dropoff_point}"
        )
        
        # Clear session data
        try:
            from controllers.web_socket import lead_appointment_state
            if wa_id in lead_appointment_state:
                del lead_appointment_state[wa_id]
        except Exception:
            pass
        
        return result
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Dropoff lead creation failed: {str(e)}")
        return {"success": False, "error": str(e)}
