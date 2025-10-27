"""
Enhanced Zoho Lead Creation Service for Lead-to-Appointment Booking Flow
Handles Zoho CRM lead creation with proper field mapping and Q5 trigger integration
"""

from datetime import datetime
from typing import Dict, Any, Optional
import requests
import json
import os

from sqlalchemy.orm import Session
from utils.zoho_auth import get_valid_access_token


class ZohoLeadService:
    """Service class for Zoho CRM lead operations"""
    
    def __init__(self):
        self.base_url = "https://www.zohoapis.in/crm/v2.1/Leads"
        self.access_token = None
    
    def _get_access_token(self) -> str:
        """Get valid access token for Zoho API"""
        if not self.access_token:
            self.access_token = get_valid_access_token()
        return self.access_token
    
    def _prepare_lead_data(
        self,
        *,
        first_name: str,
        last_name: str = "",
        email: str = "",
        phone: str = "",
        mobile: str = "",
        city: str = "",
        lead_source: str = "WhatsApp Lead-to-Appointment Flow",
        lead_status: str = "PENDING",
        company: str = "Oliva Skin & Hair Clinic",
        description: str = "",
        appointment_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Prepare lead data according to Zoho CRM API structure"""
        
        # Use mobile if provided, otherwise use phone
        contact_number = mobile if mobile else phone
        
        # Prepare description with appointment details
        desc_parts = [description] if description else []
        
        if appointment_details:
            if appointment_details.get("selected_city"):
                desc_parts.append(f"City: {appointment_details['selected_city']}")
            if appointment_details.get("selected_clinic"):
                desc_parts.append(f"Clinic: {appointment_details['selected_clinic']}")
            if appointment_details.get("custom_date"):
                desc_parts.append(f"Preferred Date: {appointment_details['custom_date']}")
            if appointment_details.get("selected_time"):
                desc_parts.append(f"Preferred Time: {appointment_details['selected_time']}")
        
        full_description = " | ".join(desc_parts) if desc_parts else "Lead from WhatsApp Lead-to-Appointment Flow"
        
        lead_data = {
            "data": [
                {
                    "First_Name": first_name,
                    "Last_Name": last_name,
                    "Email": email,
                    "Phone": contact_number,
                    "Mobile": contact_number,
                    "City": city,
                    "Lead_Source": lead_source,
                    "Lead_Status": lead_status,
                    "Company": company,
                    "Description": full_description
                }
            ],
            "trigger": [
                "approval",
                "workflow", 
                "blueprint"
            ]
        }
        
        return lead_data
    
    def create_lead(
        self,
        *,
        first_name: str,
        last_name: str = "",
        email: str = "",
        phone: str = "",
        mobile: str = "",
        city: str = "",
        lead_source: str = "WhatsApp Lead-to-Appointment Flow",
        lead_status: str = "PENDING",
        company: str = "Oliva Skin & Hair Clinic",
        description: str = "",
        appointment_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a lead in Zoho CRM"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            print(f"\n🚀 [ZOHO LEAD CREATION] Starting at {timestamp}")
            print(f"📋 [ZOHO LEAD CREATION] Customer: {first_name} {last_name}")
            print(f"📞 [ZOHO LEAD CREATION] Phone: {phone}")
            print(f"📧 [ZOHO LEAD CREATION] Email: {email}")
            print(f"🏙️ [ZOHO LEAD CREATION] City: {city}")
            print(f"📊 [ZOHO LEAD CREATION] Status: {lead_status}")
            print(f"🏢 [ZOHO LEAD CREATION] Company: {company}")
            print(f"📝 [ZOHO LEAD CREATION] Description: {description}")
            
            access_token = self._get_access_token()
            if not access_token:
                print(f"❌ [ZOHO LEAD CREATION] FAILED - No access token available")
                return {"success": False, "error": "no_access_token"}
            
            print(f"✅ [ZOHO LEAD CREATION] Access token obtained: {access_token[:20]}...")
            
            # Prepare lead data
            lead_data = self._prepare_lead_data(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                mobile=mobile,
                city=city,
                lead_source=lead_source,
                lead_status=lead_status,
                company=company,
                description=description,
                appointment_details=appointment_details
            )
            
            print(f"📦 [ZOHO LEAD CREATION] Prepared lead data:")
            print(f"   - First Name: {lead_data['data'][0]['First_Name']}")
            print(f"   - Last Name: {lead_data['data'][0]['Last_Name']}")
            print(f"   - Email: {lead_data['data'][0]['Email']}")
            print(f"   - Phone: {lead_data['data'][0]['Phone']}")
            print(f"   - Mobile: {lead_data['data'][0]['Mobile']}")
            print(f"   - City: {lead_data['data'][0]['City']}")
            print(f"   - Lead Source: {lead_data['data'][0]['Lead_Source']}")
            print(f"   - Lead Status: {lead_data['data'][0]['Lead_Status']}")
            print(f"   - Company: {lead_data['data'][0]['Company']}")
            print(f"   - Description: {lead_data['data'][0]['Description']}")
            print(f"   - Triggers: {lead_data['trigger']}")
            
            # Prepare headers
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
                "Cookie": "_zcsr_tmp=724cc9cf-75aa-4b3e-96dd-57ce0f42c37c; crmcsr=724cc9cf-75aa-4b3e-96dd-57ce0f42c37c; zalb_941ef25d4b=64bf0502158f6e506399625cae2049e9"
            }
            
            print(f"🌐 [ZOHO LEAD CREATION] Making API call to: {self.base_url}")
            print(f"📡 [ZOHO LEAD CREATION] Headers: Authorization=Zoho-oauthtoken {access_token[:20]}...")
            
            # Make API call
            response = requests.post(
                self.base_url,
                headers=headers,
                json=lead_data,
                timeout=30
            )
            
            print(f"📊 [ZOHO LEAD CREATION] API Response Status: {response.status_code}")
            print(f"📄 [ZOHO LEAD CREATION] API Response Body: {response.text}")
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                lead_id = response_data.get("data", [{}])[0].get("details", {}).get("id")
                
                print(f"🎉 [ZOHO LEAD CREATION] SUCCESS!")
                print(f"🆔 [ZOHO LEAD CREATION] Lead ID: {lead_id}")
                print(f"📅 [ZOHO LEAD CREATION] Created at: {timestamp}")
                print(f"🔗 [ZOHO LEAD CREATION] Check Zoho CRM for lead ID: {lead_id}")
                
                return {
                    "success": True,
                    "lead_id": lead_id,
                    "response": response_data
                }
            else:
                error_msg = f"API Error {response.status_code}: {response.text}"
                print(f"❌ [ZOHO LEAD CREATION] FAILED!")
                print(f"🚨 [ZOHO LEAD CREATION] Error: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            print(f"❌ [ZOHO LEAD CREATION] EXCEPTION!")
            print(f"🚨 [ZOHO LEAD CREATION] Exception: {error_msg}")
            import traceback
            print(f"📝 [ZOHO LEAD CREATION] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": error_msg}


# Global service instance
zoho_lead_service = ZohoLeadService()


async def create_lead_for_appointment(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    appointment_details: Optional[Dict[str, Any]] = None,
    lead_status: str = "PENDING",
    appointment_preference: Optional[str] = None
) -> Dict[str, Any]:
    """Create a lead in Zoho CRM for appointment booking flow.
    
    Args:
        lead_status: "PENDING", "CALL_INITIATED", or "NO_CALLBACK"
        appointment_details: Dictionary with appointment information
        appointment_preference: Additional preference text
        
    Returns a status dict.
    """
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        print(f"\n🎯 [LEAD APPOINTMENT FLOW] Starting lead creation at {timestamp}")
        print(f"📱 [LEAD APPOINTMENT FLOW] WhatsApp ID: {wa_id}")
        print(f"👤 [LEAD APPOINTMENT FLOW] Customer: {customer}")
        print(f"📊 [LEAD APPOINTMENT FLOW] Lead Status: {lead_status}")
        print(f"📋 [LEAD APPOINTMENT FLOW] Appointment Details: {appointment_details}")
        print(f"💭 [LEAD APPOINTMENT FLOW] Preference: {appointment_preference}")
        
        # Get user details from session state
        try:
            from controllers.web_socket import lead_appointment_state
            session_data = lead_appointment_state.get(wa_id, {})
            user_name = session_data.get("user_name", getattr(customer, 'name', 'Customer') or 'Customer')
            user_phone = session_data.get("user_phone", "")
            print(f"👤 [LEAD APPOINTMENT FLOW] User details from session: {user_name}, {user_phone}")
        except Exception as e:
            print(f"⚠️ [LEAD APPOINTMENT FLOW] Could not get user details from session: {e}")
            user_name = getattr(customer, 'name', 'Customer') or 'Customer'
            user_phone = ""
        
        # Prepare phone number - use user provided phone if available, otherwise use WA ID
        if user_phone and len(user_phone) == 10:
            phone_number = f"91{user_phone}"
            print(f"📞 [LEAD APPOINTMENT FLOW] Using user provided phone: {phone_number}")
        else:
            phone_number = wa_id.replace("+", "").replace(" ", "")
            if not phone_number.startswith("91"):
                phone_number = f"91{phone_number}"
            print(f"📞 [LEAD APPOINTMENT FLOW] Using WA ID as phone: {phone_number}")
        
        # Get appointment details from session state
        try:
            from controllers.web_socket import lead_appointment_state
            session_data = lead_appointment_state.get(wa_id, {})
            city = session_data.get("selected_city", "Unknown")
            clinic = session_data.get("selected_clinic", "Unknown")
            
            # Try multiple date fields
            appointment_date = (
                session_data.get("custom_date") or 
                session_data.get("selected_date") or 
                session_data.get("appointment_date") or 
                "Not specified"
            )
            
            # Try multiple time fields
            appointment_time = (
                session_data.get("selected_time") or 
                session_data.get("custom_time") or 
                session_data.get("appointment_time") or 
                "Not specified"
            )
            
            print(f"🏙️ [LEAD APPOINTMENT FLOW] Appointment details from session: {city}, {clinic}, {appointment_date}, {appointment_time}")
        except Exception as e:
            print(f"⚠️ [LEAD APPOINTMENT FLOW] Could not get appointment details from session: {e}")
            city = appointment_details.get("selected_city", "Unknown") if appointment_details else "Unknown"
            clinic = appointment_details.get("selected_clinic", "Unknown") if appointment_details else "Unknown"
            
            # Try multiple date fields from appointment_details
            appointment_date = (
                appointment_details.get("custom_date") or 
                appointment_details.get("selected_date") or 
                appointment_details.get("appointment_date") or 
                "Not specified"
            ) if appointment_details else "Not specified"
            
            # Try multiple time fields from appointment_details
            appointment_time = (
                appointment_details.get("selected_time") or 
                appointment_details.get("custom_time") or 
                appointment_details.get("appointment_time") or 
                "Not specified"
            ) if appointment_details else "Not specified"
        
        # Create description
        description_parts = [
            f"Lead from WhatsApp Lead-to-Appointment Flow",
            f"City: {city}",
            f"Clinic: {clinic}",
            f"Preferred Date: {appointment_date}",
            f"Preferred Time: {appointment_time}",
        ]
        
        if appointment_preference:
            description_parts.append(f"Preference: {appointment_preference}")
        
        description_parts.append(f"Status: {lead_status}")
        
        # Create final description
        final_description = " | ".join(description_parts)
        print(f"📝 [LEAD APPOINTMENT FLOW] Creating description: {final_description}")
        
        # Create lead using the service
        print(f"🚀 [LEAD APPOINTMENT FLOW] Calling Zoho lead service...")
        
        # Split user name into first and last name
        name_parts = user_name.strip().split(' ', 1)
        first_name = name_parts[0] if name_parts else "Customer"
        last_name = name_parts[1] if len(name_parts) > 1 else "Lead"
        
        print(f"👤 [LEAD APPOINTMENT FLOW] Name split - First: {first_name}, Last: {last_name}")
        
        result = zoho_lead_service.create_lead(
            first_name=first_name,
            last_name=last_name,
            email=getattr(customer, 'email', '') or '',
            phone=phone_number,
            mobile=phone_number,
            city=city,
            lead_source="WhatsApp Lead-to-Appointment Flow",
            lead_status=lead_status,
            company="Oliva Skin & Hair Clinic",
            description=final_description,
            appointment_details={
                "selected_city": city,
                "selected_clinic": clinic,
                "custom_date": appointment_date,
                "selected_time": appointment_time
            }
        )
        
        if result["success"]:
            print(f"🎉 [LEAD APPOINTMENT FLOW] SUCCESS! Lead created successfully!")
            print(f"🆔 [LEAD APPOINTMENT FLOW] Lead ID: {result.get('lead_id')}")
            print(f"👤 [LEAD APPOINTMENT FLOW] Customer: {user_name}")
            print(f"📱 [LEAD APPOINTMENT FLOW] WhatsApp ID: {wa_id}")
            print(f"🔗 [LEAD APPOINTMENT FLOW] Check Zoho CRM for lead ID: {result.get('lead_id')}")
        else:
            print(f"❌ [LEAD APPOINTMENT FLOW] FAILED! Lead creation failed!")
            print(f"🚨 [LEAD APPOINTMENT FLOW] Error: {result.get('error')}")
            print(f"📱 [LEAD APPOINTMENT FLOW] WhatsApp ID: {wa_id}")
        
        return result
        
    except Exception as e:
        error_msg = f"Exception: {str(e)}"
        print(f"[zoho_lead_service] ERROR - Lead creation exception: {error_msg}")
        import traceback
        print(f"[zoho_lead_service] ERROR - Traceback: {traceback.format_exc()}")
        
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
        result = await create_lead_for_appointment(
            db=db,
            wa_id=wa_id,
            customer=customer,
            appointment_details=appointment_details,
            lead_status="NO_CALLBACK",
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
        print(f"[zoho_lead_service] ERROR - Dropoff lead creation failed: {str(e)}")
        return {"success": False, "error": str(e)}


async def trigger_q5_auto_dial_event(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    appointment_details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Trigger Q5 event for auto-dial in Zoho CRM.
    
    This function handles the Q5 trigger specifically for auto-dial events.
    Q5 represents the callback confirmation step where user says "Yes" to callback.
    """
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        print(f"\n📞 [Q5 AUTO-DIAL EVENT] Starting at {timestamp}")
        print(f"📱 [Q5 AUTO-DIAL EVENT] WhatsApp ID: {wa_id}")
        print(f"👤 [Q5 AUTO-DIAL EVENT] Customer: {customer}")
        print(f"📋 [Q5 AUTO-DIAL EVENT] Appointment Details: {appointment_details}")
        print(f"🎯 [Q5 AUTO-DIAL EVENT] Action: User requested callback (Q5 Yes)")
        
        # First create the lead with CALL_INITIATED status
        print(f"🚀 [Q5 AUTO-DIAL EVENT] Creating lead with CALL_INITIATED status...")
        lead_result = await create_lead_for_appointment(
            db=db,
            wa_id=wa_id,
            customer=customer,
            appointment_details=appointment_details,
            lead_status="CALL_INITIATED",
            appointment_preference="Q5 - User requested callback"
        )
        
        if not lead_result["success"]:
            print(f"❌ [Q5 AUTO-DIAL EVENT] FAILED - Lead creation failed!")
            print(f"🚨 [Q5 AUTO-DIAL EVENT] Error: {lead_result.get('error')}")
            return {"success": False, "error": "lead_creation_failed", "details": lead_result}
        
        # Trigger auto-dial event (this would be your custom Zoho function/webhook)
        print(f"📞 [Q5 AUTO-DIAL EVENT] Lead created successfully!")
        print(f"🆔 [Q5 AUTO-DIAL EVENT] Lead ID: {lead_result.get('lead_id')}")
        print(f"📞 [Q5 AUTO-DIAL EVENT] Triggering auto-dial event...")
        
        # Here you would typically call your auto-dial API/webhook
        # auto_dial_result = await trigger_auto_dial_api(wa_id, lead_result.get('lead_id'))
        
        print(f"✅ [Q5 AUTO-DIAL EVENT] SUCCESS!")
        print(f"📞 [Q5 AUTO-DIAL EVENT] Auto-dial event triggered")
        print(f"🆔 [Q5 AUTO-DIAL EVENT] Lead ID: {lead_result.get('lead_id')}")
        print(f"📱 [Q5 AUTO-DIAL EVENT] WhatsApp ID: {wa_id}")
        print(f"🔗 [Q5 AUTO-DIAL EVENT] Check Zoho CRM for lead ID: {lead_result.get('lead_id')}")
        
        return {
            "success": True,
            "lead_result": lead_result,
            "auto_dial_triggered": True,
            "message": "Q5 auto-dial event triggered successfully"
        }
        
    except Exception as e:
        error_msg = f"Q5 auto-dial event failed: {str(e)}"
        print(f"❌ [Q5 AUTO-DIAL EVENT] EXCEPTION!")
        print(f"🚨 [Q5 AUTO-DIAL EVENT] Error: {error_msg}")
        import traceback
        print(f"📝 [Q5 AUTO-DIAL EVENT] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": error_msg}


async def handle_termination_event(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    termination_reason: str,
    appointment_details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Handle termination events (before Q5 or negative Q5 response).
    
    Creates a lead for follow-up/remarketing but does not trigger auto-dial.
    
    Args:
        termination_reason: Reason for termination (e.g., "dropped_off", "negative_q5_response")
    """
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        print(f"\n🔄 [TERMINATION EVENT] Starting at {timestamp}")
        print(f"📱 [TERMINATION EVENT] WhatsApp ID: {wa_id}")
        print(f"👤 [TERMINATION EVENT] Customer: {customer}")
        print(f"🚫 [TERMINATION EVENT] Termination Reason: {termination_reason}")
        print(f"📋 [TERMINATION EVENT] Appointment Details: {appointment_details}")
        print(f"🎯 [TERMINATION EVENT] Action: Creating follow-up lead (NO auto-dial)")
        
        # Create lead with NO_CALLBACK status for follow-up
        print(f"🚀 [TERMINATION EVENT] Creating lead with NO_CALLBACK status...")
        lead_result = await create_lead_for_appointment(
            db=db,
            wa_id=wa_id,
            customer=customer,
            appointment_details=appointment_details,
            lead_status="NO_CALLBACK",
            appointment_preference=f"Termination: {termination_reason}"
        )
        
        if lead_result["success"]:
            print(f"✅ [TERMINATION EVENT] SUCCESS!")
            print(f"🆔 [TERMINATION EVENT] Lead ID: {lead_result.get('lead_id')}")
            print(f"📱 [TERMINATION EVENT] WhatsApp ID: {wa_id}")
            print(f"🚫 [TERMINATION EVENT] Termination Reason: {termination_reason}")
            print(f"📋 [TERMINATION EVENT] Lead created for follow-up/remarketing")
            print(f"🔗 [TERMINATION EVENT] Check Zoho CRM for lead ID: {lead_result.get('lead_id')}")
        else:
            print(f"❌ [TERMINATION EVENT] FAILED!")
            print(f"🚨 [TERMINATION EVENT] Error: {lead_result.get('error')}")
            print(f"📱 [TERMINATION EVENT] WhatsApp ID: {wa_id}")
        
        return {
            "success": lead_result["success"],
            "lead_result": lead_result,
            "auto_dial_triggered": False,
            "termination_reason": termination_reason,
            "message": "Lead created for follow-up/remarketing"
        }
        
    except Exception as e:
        error_msg = f"Termination event handling failed: {str(e)}"
        print(f"❌ [TERMINATION EVENT] EXCEPTION!")
        print(f"🚨 [TERMINATION EVENT] Error: {error_msg}")
        import traceback
        print(f"📝 [TERMINATION EVENT] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": error_msg}
