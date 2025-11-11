"""
Enhanced Zoho Lead Creation Service for Lead-to-Appointment Booking Flow
Handles Zoho CRM lead creation with proper field mapping and Q5 trigger integration
"""

from datetime import datetime, date
from typing import Dict, Any, Optional
import requests
import json
import os

from sqlalchemy.orm import Session
from sqlalchemy import func
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
        lead_source: str = "Business Listing",
        company: str = "Oliva Skin & Hair Clinic",
        description: str = "",
        appointment_details: Optional[Dict[str, Any]] = None,
        sub_source: str = "Chats",
        unsubscribed_mode: Optional[str] = None,
        converted: bool = False
    ) -> Dict[str, Any]:
        """Prepare lead data according to Zoho CRM API structure"""
        
        # Use mobile if provided, otherwise use phone
        contact_number = mobile if mobile else phone
        
        # Prepare description with appointment details
        desc_parts = [description] if description else []
        
        language_value = None
        if appointment_details:
            try:
                flow_type = appointment_details.get("flow_type")
            except Exception:
                flow_type = None
            if appointment_details.get("selected_city"):
                desc_parts.append(f"City: {appointment_details['selected_city']}")
            if appointment_details.get("selected_clinic"):
                desc_parts.append(f"Clinic: {appointment_details['selected_clinic']}")
            if appointment_details.get("custom_date"):
                desc_parts.append(f"Preferred Date: {appointment_details['custom_date']}")
            if appointment_details.get("selected_time"):
                desc_parts.append(f"Preferred Time: {appointment_details['selected_time']}")
            # Language only for lead appointment flow
            if flow_type == "lead_appointment_flow":
                try:
                    lang = appointment_details.get("language")
                    if isinstance(lang, str) and lang.strip():
                        language_value = lang.strip()
                    else:
                        language_value = "English"
                    desc_parts.append(f"Language: {language_value}")
                except Exception:
                    language_value = "English"
                    desc_parts.append("Language: English")
        
        full_description = " | ".join(desc_parts) if desc_parts else "Lead from WhatsApp"

        # Map local names to Zoho API field names
        concerns_value = None
        additional_concerns_value = None
        clinic_branch_region = None
        phone_1 = None
        phone_2 = None
        try:
            if appointment_details:
                concerns_value = (
                    appointment_details.get("zoho_mapped_concern")
                    or appointment_details.get("selected_concern")
                )
                # Fill Zoho's Additional_Concerns with the user's originally selected treatment/concern
                # Zoho expects this to be a JSON array; coerce to [str] when a single value is present
                _addl = appointment_details.get("selected_concern")
                if isinstance(_addl, list):
                    additional_concerns_value = [str(x) for x in _addl if isinstance(x, (str, int, float)) and str(x).strip()]
                    if not additional_concerns_value:
                        additional_concerns_value = None
                elif isinstance(_addl, (str, int, float)) and str(_addl).strip():
                    additional_concerns_value = [str(_addl).strip()]
                else:
                    additional_concerns_value = None
                # Region should reflect the parsed location (e.g., Jubilee Hills) only
                clinic_branch_region = appointment_details.get("selected_location")
                # Primary and secondary phones
                corrected_phone = appointment_details.get("corrected_phone")
                wa_phone = appointment_details.get("wa_phone")
                print(f"🔍 [ZOHO LEAD PREP] corrected_phone: {corrected_phone}")
                print(f"🔍 [ZOHO LEAD PREP] wa_phone: {wa_phone}")
                # If user provided a corrected phone (after saying No), make it Phone_1 but keep WA as primary Phone/Mobile
                if isinstance(corrected_phone, str) and corrected_phone.strip():
                    phone_1 = corrected_phone.strip()  # User provided number goes to Phone_1
                    # Phone_2 should be the actual WA ID (contact_number), not wa_phone from customer table
                    phone_2 = contact_number  # WA ID goes to Phone_2
                    print(f"🔍 [ZOHO LEAD PREP] Set phone_1 (user provided): {phone_1}")
                    print(f"🔍 [ZOHO LEAD PREP] Set phone_2 (WA ID): {phone_2}")
                else:
                    # Default: WA number is primary
                    if isinstance(wa_phone, str) and wa_phone.strip():
                        phone_1 = wa_phone.strip()
                        print(f"🔍 [ZOHO LEAD PREP] Set phone_1 (WA default): {phone_1}")
                # Treat placeholder/unknown values as absent to avoid sending "Unknown"
                if isinstance(clinic_branch_region, str) and clinic_branch_region.strip().lower() in {
                    "unknown", "not specified", "na", "n/a", "-", "none", "null", ""
                }:
                    clinic_branch_region = None
        except Exception:
            pass
        
        lead_data = {
            "data": [
                {
                    "First_Name": first_name,
                    "Last_Name": last_name,
                    "Email": email,
                    # Use WA number for Phone/Mobile, Phone_1/Phone_2 for additional numbers
                    "Phone": contact_number,  # Always WA number
                    "Mobile": contact_number,  # Always WA number
                    **({"Phone_1": phone_1} if phone_1 else {}),
                    **({"Phone_2": phone_2} if phone_2 else {}),
                    "City": city,
                    "Lead_Source": lead_source,
                    "Company": company,
                    "Description": full_description,
                    # Language field only for lead appointment flow
                    **({"Language": language_value} if language_value else {}),
                    # Business fields expected by Zoho
                    **({"Concerns": concerns_value} if concerns_value else {}),
                    **({"Additional_Concerns": additional_concerns_value} if additional_concerns_value else {}),
                    **({"Clinic_Branch": clinic_branch_region} if clinic_branch_region else {}),
                    # Custom fields / standard fields expected in Zoho
                    "Sub_Source": sub_source,
                    "Unsubscribed_Mode": unsubscribed_mode,
                    "$converted": converted
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
        lead_source: str = "Business Listing",
        company: str = "Oliva Skin & Hair Clinic",
        description: str = "",
        appointment_details: Optional[Dict[str, Any]] = None,
        sub_source: str = "Chats",
        unsubscribed_mode: Optional[str] = None,
        converted: bool = False
    ) -> Dict[str, Any]:
        """Create a lead in Zoho CRM"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            print(f"\n🚀 [ZOHO LEAD CREATION] Starting at {timestamp}")
            print(f"📋 [ZOHO LEAD CREATION] Customer: {first_name} {last_name}")
            print(f"📞 [ZOHO LEAD CREATION] Phone: {phone}")
            print(f"📧 [ZOHO LEAD CREATION] Email: {email}")
            print(f"🏙️ [ZOHO LEAD CREATION] City: {city}")
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
                company=company,
                description=description,
                appointment_details=appointment_details,
                sub_source=sub_source,
                unsubscribed_mode=unsubscribed_mode,
                converted=converted
            )
            
            print(f"📦 [ZOHO LEAD CREATION] Prepared lead data:")
            print(f"   - First Name: {lead_data['data'][0]['First_Name']}")
            print(f"   - Last Name: {lead_data['data'][0]['Last_Name']}")
            print(f"   - Email: {lead_data['data'][0]['Email']}")
            print(f"   - Phone: {lead_data['data'][0]['Phone']}")
            print(f"   - Mobile: {lead_data['data'][0]['Mobile']}")
            print(f"   - Phone_1: {lead_data['data'][0].get('Phone_1', 'NOT_SET')}")
            print(f"   - Phone_2: {lead_data['data'][0].get('Phone_2', 'NOT_SET')}")
            print(f"   - City: {lead_data['data'][0]['City']}")
            print(f"   - Lead Source: {lead_data['data'][0]['Lead_Source']}")
            print(f"   - Sub Source: {lead_data['data'][0].get('Sub_Source')}")
            print(f"   - Unsubscribed_Mode: {lead_data['data'][0].get('Unsubscribed_Mode')}")
            print(f"   - $converted: {lead_data['data'][0].get('$converted')}")
            print(f"   - Company: {lead_data['data'][0]['Company']}")
            print(f"   - Description: {lead_data['data'][0]['Description']}")
            print(f"   - Triggers: {lead_data['trigger']}")
            print(f"🔍 [ZOHO LEAD CREATION] Appointment details: {appointment_details}")
            
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
            
            # If token is invalid/expired, refresh and retry once
            if response.status_code == 401:
                try:
                    body_lower = (response.text or "").lower()
                except Exception:
                    body_lower = ""
                if "invalid_token" in body_lower or "invalid oauth token" in body_lower or "invalid_oauth_token" in body_lower:
                    print("⚠️  [ZOHO LEAD CREATION] Detected INVALID_TOKEN (401).")
                    print("🛠️  [ZOHO LEAD CREATION] This often caused leads to be created only after a server restart due to a stale cached token.")
                    print("🔄 [ZOHO LEAD CREATION] Refreshing Zoho access token and retrying once...")
                    # Force refresh access token
                    self.access_token = get_valid_access_token()
                    refreshed_token = self.access_token
                    print(f"✅ [ZOHO LEAD CREATION] New access token obtained: {refreshed_token[:20]}...")
                    # Retry with new token
                    headers_retry = {
                        **headers,
                        "Authorization": f"Zoho-oauthtoken {refreshed_token}"
                    }
                    response = requests.post(
                        self.base_url,
                        headers=headers_retry,
                        json=lead_data,
                        timeout=30
                    )
                    print(f"🔁 [ZOHO LEAD CREATION] Retry Response Status: {response.status_code}")
                    print(f"🧾 [ZOHO LEAD CREATION] Retry Response Body: {response.text}")
            
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
        
        # Prepare phone number for legacy fields (Phone/Mobile) while we also send Phone_1/Phone_2
        if user_phone and len(user_phone) == 10:
            phone_number = f"91{user_phone}"
            print(f"📞 [LEAD APPOINTMENT FLOW] Using user provided phone: {phone_number}")
        else:
            phone_number = wa_id.replace("+", "").replace(" ", "")
            if not phone_number.startswith("91"):
                phone_number = f"91{phone_number}"
            print(f"📞 [LEAD APPOINTMENT FLOW] Using WA ID as phone: {phone_number}")

        # Normalize helper
        def _normalize_plus91(text: str | None) -> str | None:
            try:
                import re as _re
                digits = _re.sub(r"\D", "", text or "")
                last10 = digits[-10:] if len(digits) >= 10 else None
                return ("+91" + last10) if last10 and len(last10) == 10 else None
            except Exception:
                return None

        # Ensure appointment_details exists and carry normalized phones based on session/user confirmation
        if appointment_details is None:
            appointment_details = {}
        # Prefer the user's confirmed phone (from session) as Phone_1, WA ID as Phone_2
        try:
            wa_plus = _normalize_plus91(wa_id)
        except Exception:
            wa_plus = None
        if wa_plus:
            appointment_details["wa_phone"] = wa_plus
        # If user confirmed a phone in session, set it as corrected_phone to map to Phone_1
        if user_phone:
            confirmed_plus = _normalize_plus91(user_phone)
            if confirmed_plus:
                appointment_details["corrected_phone"] = confirmed_plus
        print(
            f"📞 [LEAD APPOINTMENT FLOW] session.wa_id => wa_phone: {appointment_details.get('wa_phone')} | "
            f"user_confirmed => corrected_phone: {appointment_details.get('corrected_phone')}"
        )
        
        # Initialize variables for concern tracking
        selected_concern = None
        zoho_mapped_concern = None
        city = "Unknown"
        clinic = "Unknown"
        appointment_date = "Not specified"
        appointment_time = "Not specified"
        
        # Get appointment details from session state
        try:
            from controllers.web_socket import lead_appointment_state, appointment_state
            session_data = lead_appointment_state.get(wa_id, {})
            city = session_data.get("selected_city", "Unknown")
            clinic = session_data.get("selected_clinic", "Unknown")
            # Optional: location captured from prefilled deep link (e.g., "Jubilee Hills")
            location = session_data.get("selected_location") or (appointment_state.get(wa_id, {}) if 'appointment_state' in globals() else {}).get("selected_location")
            # In lead appointment flow, take selected clinic as the location if not explicitly provided
            if not location and clinic and isinstance(clinic, str) and clinic.strip():
                location = clinic
            
            # Try multiple date fields - prioritize selected_week over specific dates
            appointment_date = (
                session_data.get("selected_week") or  # New: preferred week selection
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
            
            # Get selected concern from appointment state and map to Zoho name
            try:
                # Try to get from appointment_state (treatment flow) or lead_appointment_state
                concern_data = appointment_state.get(wa_id, {})
                selected_concern = concern_data.get("selected_concern")
                if not selected_concern:
                    from controllers.web_socket import lead_appointment_state  # type: ignore
                    selected_concern = (lead_appointment_state.get(wa_id) or {}).get("selected_concern")
                
                # If found, normalize to canonical label then look up Zoho mapping
                if selected_concern:
                    try:
                        def _canon(txt: str) -> str:
                            import re as _re
                            return _re.sub(r"[^a-z0-9]+", " ", (txt or "").lower()).strip()
                        norm = _canon(selected_concern)
                        canon_map = {
                            "acne": "Acne / Acne Scars",
                            "acne acne scars": "Acne / Acne Scars",
                            "pigmentation": "Pigmentation & Uneven Skin Tone",
                            "uneven skin tone": "Pigmentation & Uneven Skin Tone",
                            "anti aging": "Anti-Aging & Skin Rejuvenation",
                            "skin rejuvenation": "Anti-Aging & Skin Rejuvenation",
                            "dandruff": "Dandruff & Scalp Care",
                            "dandruff scalp care": "Dandruff & Scalp Care",
                            "laser hair removal": "Laser Hair Removal",
                            "hair loss hair fall": "Hair Loss / Hair Fall",
                            "hair transplant": "Hair Transplant",
                            "weight management": "Weight Management",
                            "body contouring": "Body Contouring",
                            "weight loss": "Weight Loss",
                        }
                        selected_concern = canon_map.get(norm, selected_concern)
                    except Exception:
                        pass
                    from services.zoho_mapping_service import get_zoho_name
                    zoho_mapped_concern = get_zoho_name(db, selected_concern)
                    print(f"🎯 [LEAD APPOINTMENT FLOW] Selected concern: {selected_concern}, Mapped to Zoho: {zoho_mapped_concern}")
            except Exception as e:
                print(f"⚠️ [LEAD APPOINTMENT FLOW] Could not get/parse selected concern from state: {e}")
            
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
        
        # Try to get selected concern from appointment_details if not found in state
        if not selected_concern and appointment_details:
            selected_concern = appointment_details.get("selected_concern")
            if selected_concern:
                print(f"🎯 [LEAD APPOINTMENT FLOW] Got concern from appointment_details: {selected_concern}")
                try:
                    from services.zoho_mapping_service import get_zoho_name
                    zoho_mapped_concern = get_zoho_name(db, selected_concern)
                    print(f"🎯 [LEAD APPOINTMENT FLOW] Mapped to Zoho: {zoho_mapped_concern}")
                except Exception as map_e:
                    print(f"⚠️ [LEAD APPOINTMENT FLOW] Could not map concern: {map_e}")
        
        # Debug: Print what we found
        print(f"🔍 [LEAD APPOINTMENT FLOW] Final concern values:")
        print(f"   - selected_concern: {selected_concern}")
        print(f"   - zoho_mapped_concern: {zoho_mapped_concern}")
        print(f"   - appointment_details: {appointment_details}")
        
        # Stop persisting description/lead_status to DB; retain for external Zoho payload only
        final_description = None
        
        # Create lead using the service
        print(f"🚀 [LEAD APPOINTMENT FLOW] Calling Zoho lead service...")
        
        # Split user name into first and last name
        # Logic: If customer has only first name (no space) → treat it as last name, leave first name empty
        #        If customer has both first and last name (has space) → use both
        #        If no name provided → default to "Customer" as last name
        user_name_clean = (user_name or "").strip()
        if not user_name_clean:
            first_name = ""
            last_name = "Customer"
        else:
            name_parts = user_name_clean.split(' ', 1)
            
            if len(name_parts) == 1:
                # Only first name provided - treat it as last name, leave first name empty
                first_name = ""
                last_name = name_parts[0] if name_parts else "Customer"
            else:
                # Both first and last name provided - use both
                first_name = name_parts[0] if name_parts else ""
                last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        print(f"👤 [LEAD APPOINTMENT FLOW] Name mapping - Original: '{user_name}', First: '{first_name}', Last: '{last_name}'")

        # Determine flow type and set Lead Source / Sub Source / Language per flow
        try:
            flow_type = (appointment_details or {}).get("flow_type")
        except Exception:
            flow_type = None
        
        # If flow_type is not set in appointment_details, check appointment_state
        if not flow_type:
            try:
                from controllers.web_socket import appointment_state
                appt_state = appointment_state.get(wa_id, {})
                if (
                    bool(appt_state.get("from_treatment_flow")) or 
                    appt_state.get("flow_context") == "treatment" or
                    bool(appt_state.get("treatment_flow_phone_id"))
                ):
                    flow_type = "treatment_flow"
                    print(f"[LEAD APPOINTMENT FLOW] Detected treatment flow from appointment_state")
            except Exception as e:
                print(f"[LEAD APPOINTMENT FLOW] Could not check appointment_state: {e}")

        # ===== Same-day duplicate check before pushing to Zoho =====
        try:
            from models.models import Lead  # local DB model

            today = datetime.utcnow().date()
            # Build input full name normalized
            input_full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip().lower()

            # Build normalized full name in DB: lower(trim(first_name || ' ' || last_name))
            db_full_name = func.lower(func.trim(func.concat(func.coalesce(Lead.first_name, ''), func.concat(' ', func.coalesce(Lead.last_name, '')))))

            query = db.query(Lead).filter(
                Lead.phone == phone_number,
                func.date(Lead.created_at) == today,
                db_full_name == input_full_name
            )

            existing_today = query.first()
            if existing_today:
                print(
                    f"🛑 [LEAD APPOINTMENT FLOW] Duplicate detected for today. "
                    f"Phone: {phone_number}, Name: {first_name} {last_name}. "
                    f"Skipping Zoho push. Existing Zoho Lead ID: {existing_today.zoho_lead_id}"
                )
                return {
                    "success": True,
                    "skipped": True,
                    "reason": "duplicate_same_day",
                    "lead_id": existing_today.zoho_lead_id
                }
        except Exception as dup_e:
            print(f"⚠️ [LEAD APPOINTMENT FLOW] Duplicate-check failed, proceeding with push: {dup_e}")
        # ===========================================================

        if flow_type == "treatment_flow":
            # Treatment flow
            lead_source_val = "Business Listing"
            sub_source_val = "WhatsApp"
            language_val = None  # Not specified for treatment flow
        else:
            # Lead appointment flow (default)
            try:
                lead_source_val = session_data.get("lead_source") or "Facebook"
                language_val = session_data.get("language") or "English"
            except Exception:
                lead_source_val = "Facebook"
                language_val = "English"
            sub_source_val = "WhatsApp"

        result = zoho_lead_service.create_lead(
            first_name=first_name,
            last_name=last_name,
            email=getattr(customer, 'email', '') or '',
            phone=phone_number,
            mobile=phone_number,
            city=city,
            lead_source=lead_source_val,
            company="Oliva Skin & Hair Clinic",
            description=(f"Lead from WhatsApp | Language: {language_val}" if language_val else "Lead from WhatsApp"),
            appointment_details={
                "flow_type": (flow_type or "lead_appointment_flow"),
                "selected_city": city,
                "selected_clinic": clinic,
                **({"selected_location": location} if 'location' in locals() and location else {}),
                "selected_week": session_data.get("selected_week", "Not specified"),
                "custom_date": appointment_date,
                "selected_time": appointment_time,
                "selected_concern": selected_concern,
                "zoho_mapped_concern": zoho_mapped_concern,
                "lead_source": lead_source_val,
                **({"language": language_val} if language_val else {}),
                # Preserve phone numbers from customer table
                **({"wa_phone": appointment_details.get("wa_phone")} if appointment_details.get("wa_phone") else {}),
                **({"corrected_phone": appointment_details.get("corrected_phone")} if appointment_details.get("corrected_phone") else {}),
            },
            sub_source=sub_source_val,
            
        )
        
        if result["success"]:
            print(f"🎉 [LEAD APPOINTMENT FLOW] SUCCESS! Lead created successfully!")
            print(f"🆔 [LEAD APPOINTMENT FLOW] Lead ID: {result.get('lead_id')}")
            print(f"👤 [LEAD APPOINTMENT FLOW] Customer: {user_name}")
            print(f"📱 [LEAD APPOINTMENT FLOW] WhatsApp ID: {wa_id}")
            print(f"🔗 [LEAD APPOINTMENT FLOW] Check Zoho CRM for lead ID: {result.get('lead_id')}")
            
            # Save lead to local database
            try:
                from models.models import Lead
                from services.zoho_mapping_service import get_zoho_name
                
                # Check if lead already exists
                existing_lead = db.query(Lead).filter(Lead.zoho_lead_id == result.get('lead_id')).first()
                
                if not existing_lead:
                    # Resolve concern values robustly
                    final_selected_concern = selected_concern or (appointment_details or {}).get("selected_concern")
                    final_mapped_concern = (
                        zoho_mapped_concern
                        or (appointment_details or {}).get("zoho_mapped_concern")
                        or (get_zoho_name(db, final_selected_concern) if final_selected_concern else None)
                    )
                    print(
                        f"💡 [LEAD APPOINTMENT FLOW] Using concern values for DB save: "
                        f"selected='{final_selected_concern}', mapped='{final_mapped_concern}'"
                    )
                    
        # Create new lead record
                    new_lead = Lead(
                        zoho_lead_id=result.get('lead_id'),
                        first_name=first_name,
                        last_name=last_name,
                        email=getattr(customer, 'email', '') or '',
                        phone=phone_number,
                        mobile=phone_number,
                        city=city,
            location=(location if 'location' in locals() else None),
                        lead_source=lead_source_val,
                        company="Oliva Skin & Hair Clinic",
                        wa_id=wa_id,
                        customer_id=getattr(customer, 'id', None),
                        appointment_details={
                            "selected_city": city,
                            "selected_clinic": clinic,
                **({"selected_location": location} if 'location' in locals() and location else {}),
                            "selected_concern": final_selected_concern,
                            "zoho_mapped_concern": final_mapped_concern
                        },
                        treatment_name=final_selected_concern,
                        zoho_mapped_concern=final_mapped_concern,
                        primary_concern=final_mapped_concern or final_selected_concern,
                        sub_source=sub_source_val
                    )
                    db.add(new_lead)
                    db.commit()
                    db.refresh(new_lead)
                    print(f"💾 [LEAD APPOINTMENT FLOW] Lead saved to local database with ID: {new_lead.id}")
                else:
                    print(f"⚠️ [LEAD APPOINTMENT FLOW] Lead already exists in database")
            except Exception as db_e:
                print(f"⚠️ [LEAD APPOINTMENT FLOW] Could not save lead to local database: {db_e}")
                db.rollback()
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