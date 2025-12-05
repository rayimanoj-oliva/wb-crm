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
            "source": "Facebook"
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
    """
    Legacy lead-appointment Zoho lead creation.

    NOTE: This path is now DISABLED in favour of the unified zoho_lead_service
    (used from treatment flow and Follow-Up 2 drop-off logic).

    We intentionally skip creating leads here to avoid duplicate / incorrect
    Lead Source values such as "Facebook" (for lead appointment flow) or "Business Listing" (for treatment flow)
    when the marketing treatment flow is in use.
    """

    # Hard disable: do not create any leads from this legacy integration.
    print(
        "[lead_appointment_flow] INFO - trigger_zoho_lead_creation is disabled; "
        "no Zoho lead will be created from this path."
    )
    return {
        "success": True,
        "skipped": True,
        "reason": "legacy_zoho_lead_creation_disabled",
    }

    # The original implementation is left below for reference, but is no longer used.
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
        
        # De-duplication: Check local DB first (within last 24 hours), then Zoho
        try:
            from models.models import Lead as _Lead
            from sqlalchemy import or_, func
            from datetime import datetime as _dt, timedelta as _td

            def _digits_only(val: str | None) -> str:
                try:
                    import re as _re
                    return _re.sub(r"\D", "", val or "")
                except Exception:
                    return val or ""

            phone_digits = _digits_only(phone_number)
            last10 = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits

            phone_variants = {
                phone_digits,
                last10 if len(last10) == 10 else "",
                f"+{phone_digits}" if phone_digits else "",
                f"+91{last10}" if len(last10) == 10 else "",
                f"91{last10}" if len(last10) == 10 else "",
            }
            phone_variants = {p for p in phone_variants if p}

            # Only check for duplicates within last 24 hours
            window_start = _dt.utcnow() - _td(hours=24)

            criteria = [_Lead.wa_id == wa_id]
            if phone_variants:
                criteria.append(_Lead.phone.in_(phone_variants))
                criteria.append(_Lead.mobile.in_(phone_variants))
            customer_id_val = getattr(customer, "id", None)
            if customer_id_val:
                criteria.append(_Lead.customer_id == customer_id_val)

            existing_any = (
                db.query(_Lead)
                .filter(or_(*criteria))
                .filter(_Lead.created_at >= window_start)
                .order_by(_Lead.created_at.desc())
                .first()
            )
            if existing_any:
                print(f"✅ [zoho_integration] Duplicate prevented: existing lead found for {wa_id} (lead_id={existing_any.zoho_lead_id})")
                return {"success": True, "duplicate": True, "lead_id": existing_any.zoho_lead_id}
        except Exception as _e:
            print(f"⚠️ [zoho_integration] De-dup check failed: {_e}")

        # Zoho-side duplicate guard by phone
        try:
            from controllers.components.lead_appointment_flow.zoho_lead_service import zoho_lead_service
            existing_zoho = zoho_lead_service.find_existing_lead_by_phone(phone_number)
            if existing_zoho and isinstance(existing_zoho, dict):
                lead_id_existing = str(existing_zoho.get("id") or existing_zoho.get("Id") or "")
                if lead_id_existing:
                    print(f"✅ [zoho_integration] Duplicate prevented via Zoho search by phone. lead_id={lead_id_existing}")
                    return {"success": True, "duplicate": True, "lead_id": lead_id_existing}
        except Exception as _e:
            print(f"⚠️ [zoho_integration] Zoho-side duplicate check failed: {_e}")
        
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
        
        # Check if this is a treatment flow context
        is_treatment_flow = False
        try:
            from controllers.web_socket import appointment_state
            appt_state = appointment_state.get(wa_id, {})
            is_treatment_flow = (
                bool(appt_state.get("from_treatment_flow")) or 
                appt_state.get("flow_context") == "treatment" or
                bool(appt_state.get("treatment_flow_phone_id"))
            )
            print(f"[lead_appointment_flow] DEBUG - Is treatment flow: {is_treatment_flow}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not check treatment flow context: {e}")
        
        # Create lead description
        description_parts = [
            f"Lead from Facebook",
            f"City: {city}",
            f"Clinic: {clinic}",
            f"Preferred Date: {appointment_date}",
        ]
        
        if appointment_preference:
            description_parts.append(f"Preference: {appointment_preference}")
        
        description_parts.append(f"Status: {lead_status}")
        
        # Name handling per requirement:
        # - If only first name is present, treat it as Last_Name and leave First_Name empty
        # - If both first and last are present, fill both accordingly
        try:
            import re as _re
            tokens = [t for t in _re.split(r"\s+", (user_name or "").strip()) if t]
        except Exception:
            tokens = [(user_name or "").strip()] if (user_name or "").strip() else []

        if len(tokens) >= 2:
            first_name_val = tokens[0]
            last_name_val = " ".join(tokens[1:])
        elif len(tokens) == 1:
            first_name_val = ""
            last_name_val = tokens[0]
        else:
            first_name_val = ""
            last_name_val = "Customer"

        # Set Lead Source and Sub Source based on flow type
        if is_treatment_flow:
            lead_source_val = "Business Listing"
            sub_source_val = "WhatsApp Dial"  # Changed from "WhatsApp" to "WhatsApp Dial" for treatment flow
        else:
            # Lead appointment flow → always use "Facebook" as lead source
            lead_source_val = "Facebook"
            sub_source_val = None

        # Simplified lead data without custom fields to avoid API errors
        lead_data = {
            "data": [
                {
                    "First_Name": first_name_val,
                    "Last_Name": last_name_val,
                    "Phone": phone_number,
                    "Email": getattr(customer, 'email', '') or '',
                    "Lead_Source": lead_source_val,
                    "Lead_Status": lead_status,
                    "Company": "Oliva Skin & Hair Clinic",
                    "Description": " | ".join(description_parts),
                    "City": city,
                }
            ]
        }
        
        # Add Sub_Source only if it's set (for treatment flow)
        if sub_source_val:
            lead_data["data"][0]["Sub_Source"] = sub_source_val
        
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