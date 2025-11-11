"""
Zoho CRM Integration for Lead-to-Appointment Booking Flow
Handles Zoho Auto-Dial and Lead creation APIs
"""

from datetime import datetime
from typing import Dict, Any, Optional
import requests
import json

from sqlalchemy.orm import Session
from sqlalchemy import func
from utils.zoho_auth import get_valid_access_token
from utils.whatsapp import send_message_to_waid
from marketing.services.lead_metrics import log_lead_metric, infer_step_from_details


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
            f"Lead from WhatsApp Lead-to-Appointment Flow",
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
            sub_source_val = "WhatsApp"
        else:
            lead_source_val = "WhatsApp Lead-to-Appointment Flow"
            sub_source_val = None

        # Infer step for logging
        try:
            step_for_log = infer_step_from_details(
                {
                    **(appointment_details or {}),
                    "selected_city": city,
                    "selected_clinic": clinic,
                    "selected_date": appointment_date if appointment_date != "Not specified" else None,
                }
            )
        except Exception:
            step_for_log = "start"

        # Same-day duplicate check in legacy path as well
        try:
            from models.models import Lead
            # Build name tokens same as below
            import re as _re
            tokens_for_dup = [t for t in _re.split(r"\s+", (user_name or '').strip()) if t]
            if len(tokens_for_dup) >= 2:
                dup_first = tokens_for_dup[0]
                dup_last = " ".join(tokens_for_dup[1:])
            elif len(tokens_for_dup) == 1:
                dup_first = ""
                dup_last = tokens_for_dup[0]
            else:
                dup_first = ""
                dup_last = "Customer"

            input_full_name = f"{dup_first} {dup_last}".strip().lower()
            db_full_name = func.lower(func.trim(func.concat(func.coalesce(Lead.first_name, ''), func.concat(' ', func.coalesce(Lead.last_name, '')))))

            today = datetime.utcnow().date()
            dup = db.query(Lead).filter(
                Lead.phone == phone_number,
                func.date(Lead.created_at) == today,
                db_full_name == input_full_name
            ).first()
            if dup:
                print(f"[lead_appointment_flow] DEBUG - Duplicate (legacy path) found for today, skipping push.")
                try:
                    log_lead_metric(
                        event_type="duplicate_same_day",
                        wa_id=wa_id,
                        phone=phone_number,
                        full_name=input_full_name,
                        step=step_for_log,
                        details="Skipped Zoho push (legacy path) due to same-day duplicate",
                        meta={"existing_zoho_lead_id": dup.zoho_lead_id},
                    )
                except Exception:
                    pass
                return {"success": True, "skipped": True, "reason": "duplicate_same_day", "lead_id": dup.zoho_lead_id}
        except Exception as _e_dup:
            print(f"[lead_appointment_flow] WARNING - Legacy duplicate check failed: {_e_dup}")

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
        # Metrics: push attempt
        try:
            log_lead_metric(
                event_type="push_attempt",
                wa_id=wa_id,
                phone=phone_number,
                full_name=user_name,
                step=step_for_log,
                details=f"Attempting Zoho push (legacy path, source={lead_source_val})",
                meta={"city": city, "clinic": clinic},
            )
        except Exception:
            pass
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
            # Metrics: success
            try:
                log_lead_metric(
                    event_type="push_success",
                    wa_id=wa_id,
                    phone=phone_number,
                    full_name=user_name,
                    step=step_for_log,
                    details="Zoho lead created successfully (legacy path)",
                    meta={"zoho_lead_id": lead_id},
                )
            except Exception:
                pass

            # Save to local DB to keep parity with service path
            try:
                from models.models import Lead as LeadModel
                existing = db.query(LeadModel).filter(LeadModel.zoho_lead_id == lead_id).first()
                if not existing:
                    new_lead = LeadModel(
                        zoho_lead_id=lead_id,
                        first_name=lead_data["data"][0]["First_Name"] or "",
                        last_name=lead_data["data"][0]["Last_Name"] or "",
                        email=getattr(customer, 'email', '') or '',
                        phone=phone_number,
                        mobile=phone_number,
                        city=city,
                        lead_source=lead_source_val,
                        company="Oliva Skin & Hair Clinic",
                        wa_id=wa_id,
                        appointment_details={
                            "selected_city": city,
                            "selected_clinic": clinic,
                            "custom_date": appointment_date,
                        },
                        sub_source=(sub_source_val or None),
                    )
                    db.add(new_lead)
                    db.commit()
                    db.refresh(new_lead)
                    print(f"[zoho_integration] DEBUG - Lead saved to DB (legacy path): {new_lead.id}")
            except Exception as _save_e:
                print(f"[zoho_integration] WARNING - Failed to save lead to DB (legacy path): {_save_e}")
                db.rollback()

            return {"success": True, "lead_id": lead_id, "response": response_data}
        else:
            error_msg = f"API Error {response.status_code}: {response.text}"
            print(f"[lead_appointment_flow] ERROR - Lead creation failed: {error_msg}")
            
            # Log failed lead creation
            print(f"[zoho_integration] DEBUG - Lead creation failed: {wa_id}, Error: {error_msg}")
            try:
                log_lead_metric(
                    event_type="push_failed",
                    wa_id=wa_id,
                    phone=phone_number,
                    full_name=user_name,
                    step=step_for_log,
                    details=error_msg,
                )
            except Exception:
                pass
            
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
