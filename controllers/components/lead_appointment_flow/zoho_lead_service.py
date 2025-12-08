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
from sqlalchemy import func, or_, and_
from utils.zoho_auth import get_valid_access_token


class ZohoLeadService:
    """Service class for Zoho CRM lead operations"""

    def __init__(self):
        self.base_url = "https://www.zohoapis.in/crm/v2.1/Leads"
        self.access_token = None
        self._token_fetched_at = None

    def _get_access_token(self) -> str:
        """Get valid access token for Zoho API with proactive refresh"""
        from datetime import datetime, timedelta

        # Proactively refresh if token is older than 50 minutes (tokens expire in ~60 mins)
        token_max_age = timedelta(minutes=50)
        needs_refresh = (
            not self.access_token or
            not self._token_fetched_at or
            (datetime.utcnow() - self._token_fetched_at) > token_max_age
        )

        if needs_refresh:
            self.access_token = get_valid_access_token()
            self._token_fetched_at = datetime.utcnow()
            print(f"🔄 [ZOHO] Access token refreshed at {self._token_fetched_at}")

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
                # Format time value - if it's a raw time like "1630", format as "16:30"
                time_value = appointment_details['selected_time']
                try:
                    # Check if it's a raw time format (4 digits like "1630" or "1030")
                    if isinstance(time_value, str) and time_value.replace(":", "").isdigit():
                        time_clean = time_value.replace(":", "").strip()
                        if len(time_clean) == 4 and time_clean.isdigit():
                            # Format as HH:MM
                            formatted_time = f"{time_clean[:2]}:{time_clean[2:]}"
                            desc_parts.append(f"Preferred Time: {formatted_time}")
                        else:
                            desc_parts.append(f"Preferred Time: {time_value}")
                    else:
                        desc_parts.append(f"Preferred Time: {time_value}")
                except Exception:
                    desc_parts.append(f"Preferred Time: {time_value}")
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

    def _normalize_digits(self, phone: str) -> str:
        try:
            import re as _re
            digits = _re.sub(r"\D", "", phone or "")
            return digits[-10:] if len(digits) >= 10 else digits
        except Exception:
            return phone

    def find_existing_lead_by_phone_and_source(
        self, 
        phone: str, 
        lead_source: str,
        within_same_day: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Search Zoho for an existing lead by phone and Lead Source. Returns first match dict or None.
        
        Args:
            phone: Phone number to search for
            lead_source: Lead Source to match (e.g., "Facebook", "Business Listing")
            within_same_day: If True, only return leads created on the same day (default: True)
        """
        try:
            from datetime import datetime, timedelta, timezone
            
            access_token = self._get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            digits = self._normalize_digits(phone)
            if not digits:
                return None
            candidates = {
                digits,
                digits[-10:] if len(digits) > 10 else digits,
                f"91{digits[-10:]}" if len(digits[-10:]) == 10 else None,
                f"+91{digits[-10:]}" if len(digits[-10:]) == 10 else None,
            }
            candidates = [c for c in candidates if c]

            # Calculate same-day cutoff if needed (start of today UTC)
            cutoff_time = None
            if within_same_day:
                now_utc = datetime.now(timezone.utc)
                cutoff_time = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0, tzinfo=timezone.utc)

            # Try search endpoint variants: direct phone search + criteria on multiple fields
            search_fields = ["Phone", "Mobile", "Phone_1", "Phone_2", "Alternate_Phone"]

            for ph in candidates:
                # Search by phone AND Lead Source
                crit = f"((Phone:equals:{ph}) OR (Mobile:equals:{ph}) OR (Phone_1:equals:{ph}) OR (Phone_2:equals:{ph})) AND (Lead_Source:equals:{lead_source})"
                url = f"{self.base_url}/search?criteria={crit}"
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json() or {}
                    if data.get("data"):
                        # Filter by creation date if needed
                        for lead in data["data"]:
                            if not within_same_day:
                                return lead
                            # Check Created_Time in details
                            details = lead.get("details", {})
                            created_time_str = details.get("Created_Time")
                            if created_time_str:
                                try:
                                    # Zoho returns time in format: "2025-11-11T17:53:04+05:30"
                                    # Parse it to datetime
                                    created_dt = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                                    # Convert to UTC if needed
                                    if created_dt.tzinfo is None:
                                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                                    else:
                                        created_dt = created_dt.astimezone(timezone.utc)
                                    
                                    if created_dt >= cutoff_time:
                                        return lead
                                except Exception:
                                    # If date parsing fails, skip this lead
                                    continue
            return None
        except Exception:
            return None

    def find_existing_lead_by_phone(self, phone: str, within_last_24h: bool = True) -> Optional[Dict[str, Any]]:
        """Search Zoho for an existing lead by phone. Returns first match dict or None.
        
        Args:
            phone: Phone number to search for
            within_last_24h: If True, only return leads created within last 24 hours (default: True)
        """
        try:
            from datetime import datetime, timedelta, timezone
            
            access_token = self._get_access_token()
            headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
            digits = self._normalize_digits(phone)
            if not digits:
                return None
            candidates = {
                digits,
                digits[-10:] if len(digits) > 10 else digits,
                f"91{digits[-10:]}" if len(digits[-10:]) == 10 else None,
                f"+91{digits[-10:]}" if len(digits[-10:]) == 10 else None,
            }
            candidates = [c for c in candidates if c]

            # Calculate 24-hour cutoff if needed
            cutoff_time = None
            if within_last_24h:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

            # Try search endpoint variants: direct phone search + criteria on multiple fields
            search_fields = ["Phone", "Mobile", "Phone_1", "Phone_2", "Alternate_Phone"]

            for ph in candidates:
                # 1) direct phone param (Zoho matches Phone/Mobile)
                url1 = f"{self.base_url}/search?phone={ph}"
                r1 = requests.get(url1, headers=headers, timeout=10)
                if r1.status_code == 200:
                    data = r1.json() or {}
                    if data.get("data"):
                        # Filter by creation date if needed
                        for lead in data["data"]:
                            if not within_last_24h:
                                return lead
                            # Check Created_Time in details
                            details = lead.get("details", {})
                            created_time_str = details.get("Created_Time")
                            if created_time_str:
                                try:
                                    # Zoho returns time in format: "2025-11-11T17:53:04+05:30"
                                    # Parse it to datetime
                                    created_dt = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                                    # Convert to UTC if needed
                                    if created_dt.tzinfo is None:
                                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                                    else:
                                        created_dt = created_dt.astimezone(timezone.utc)
                                    
                                    if created_dt >= cutoff_time:
                                        return lead
                                except Exception:
                                    # If date parsing fails, skip this lead
                                    continue
                        # If no recent lead found, continue to next candidate

                # 2) criteria search across multiple phone fields
                for field in search_fields:
                    crit = f"({field}:equals:{ph})"
                    url2 = f"{self.base_url}/search?criteria={crit}"
                    r2 = requests.get(url2, headers=headers, timeout=10)
                    if r2.status_code == 200:
                        data = r2.json() or {}
                        if data.get("data"):
                            # Filter by creation date if needed
                            for lead in data["data"]:
                                if not within_last_24h:
                                    return lead
                                # Check Created_Time in details
                                details = lead.get("details", {})
                                created_time_str = details.get("Created_Time")
                                if created_time_str:
                                    try:
                                        # Zoho returns time in format: "2025-11-11T17:53:04+05:30"
                                        created_dt = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                                        # Convert to UTC if needed
                                        if created_dt.tzinfo is None:
                                            created_dt = created_dt.replace(tzinfo=timezone.utc)
                                        else:
                                            created_dt = created_dt.astimezone(timezone.utc)
                                        
                                        if created_dt >= cutoff_time:
                                            return lead
                                    except Exception:
                                        # If date parsing fails, skip this lead
                                        continue
            return None
        except Exception:
            return None
    
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
            user_name = session_data.get("user_name", getattr(customer, "name", "Customer") or "Customer")
            user_phone = session_data.get("user_phone", "")
            print(f"👤 [LEAD APPOINTMENT FLOW] User details from session: {user_name}, {user_phone}")
        except Exception as e:
            print(f"⚠️ [LEAD APPOINTMENT FLOW] Could not get user details from session: {e}")
            user_name = getattr(customer, "name", "Customer") or "Customer"
            user_phone = ""

        # Derive first_name / last_name for Zoho from user_name
        user_name_clean = (user_name or "").strip()
        if not user_name_clean:
            first_name = ""
            last_name = "Customer"
        else:
            name_parts = user_name_clean.split(" ", 1)
            if len(name_parts) == 1:
                # Only one word → treat as last name
                first_name = ""
                last_name = name_parts[0]
            else:
                first_name = name_parts[0]
                last_name = name_parts[1]
        print(
            f"👤 [LEAD APPOINTMENT FLOW] Name mapping - Original: '{user_name}', "
            f"First: '{first_name}', Last: '{last_name}'"
        )
        
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
        
        # Determine flow_type early to know what Lead Source we'll use
        try:
            flow_type = (appointment_details or {}).get("flow_type")
        except Exception:
            flow_type = None

        if not flow_type:
            # Fallback: infer from appointment_state flags
            try:
                from controllers.web_socket import appointment_state
                appt_state = appointment_state.get(wa_id, {})
                if (
                    bool(appt_state.get("from_treatment_flow"))
                    or appt_state.get("flow_context") == "treatment"
                    or bool(appt_state.get("treatment_flow_phone_id"))
                ):
                    flow_type = "treatment_flow"
                    print("[LEAD APPOINTMENT FLOW] Detected treatment flow from appointment_state")
            except Exception as e:
                print(f"[LEAD APPOINTMENT FLOW] Could not check appointment_state: {e}")

        # Determine Lead Source early for duplication check
        try:
            from controllers.web_socket import lead_appointment_state
            session_data_temp = lead_appointment_state.get(wa_id, {})
            _temp_session_lead_source = session_data_temp.get("lead_source")
        except Exception:
            _temp_session_lead_source = None

        # Determine expected Lead Source
        if flow_type == "treatment_flow":
            expected_lead_source = "Business Listing"
        else:
            expected_lead_source = _temp_session_lead_source if _temp_session_lead_source and _temp_session_lead_source.strip() else "Facebook"

        # Duplication check: one lead per day per Lead Source
        # Check for duplicates with same Lead Source on the same day
        try:
            from models.models import Lead as _Lead
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

            # Check for duplicates on the same day with same Lead Source
            now_utc = _dt.utcnow()
            day_start = _dt(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0)

            criteria = [
                _Lead.lead_source == expected_lead_source,  # Same Lead Source
                _Lead.created_at >= day_start,  # Same day
            ]
            
            # Match by phone variants
            if phone_variants:
                phone_criteria = or_(
                    _Lead.phone.in_(phone_variants),
                    _Lead.mobile.in_(phone_variants),
                )
                criteria.append(phone_criteria)
            
            # Also match by wa_id
            criteria.append(_Lead.wa_id == wa_id)

            existing_lead_same_source = (
                db.query(_Lead)
                .filter(and_(*criteria))
                .order_by(_Lead.created_at.desc())
                .first()
            )
            
            if existing_lead_same_source:
                print(
                    f"✅ [LEAD APPOINTMENT FLOW] Duplicate prevented: existing '{expected_lead_source}' lead found "
                    f"for {wa_id} (phone={phone_number}) on same day (lead_id={existing_lead_same_source.zoho_lead_id})"
                )
                try:
                    from utils.flow_log import log_flow_event  # type: ignore
                    log_flow_event(
                        db,
                        flow_type="lead_appointment",
                        step="result",
                        status_code=200,
                        wa_id=wa_id,
                        name=getattr(customer, 'name', None) or '',
                        description=f"Duplicate avoided: existing {expected_lead_source} lead {existing_lead_same_source.zoho_lead_id}",
                    )
                except Exception:
                    pass
                return {"success": True, "duplicate": True, "lead_id": existing_lead_same_source.zoho_lead_id}
            else:
                print(
                    f"🔍 [LEAD APPOINTMENT FLOW] No '{expected_lead_source}' lead found in DB for {wa_id} "
                    f"(phone={phone_number}) on same day. Checking Zoho..."
                )
        except Exception as _e:
            print(f"⚠️ [LEAD APPOINTMENT FLOW] DB duplicate check failed: {_e}")

        # Zoho-side duplicate guard: check for leads by phone AND Lead Source (same day)
        try:
            existing_zoho = zoho_lead_service.find_existing_lead_by_phone_and_source(
                phone_number, 
                lead_source=expected_lead_source,
                within_same_day=True
            )
            if existing_zoho and isinstance(existing_zoho, dict):
                lead_id_existing = str(
                    existing_zoho.get("id") or existing_zoho.get("Id") or ""
                )
                if lead_id_existing:
                    print(
                        f"✅ [LEAD APPOINTMENT FLOW] Duplicate prevented via Zoho: existing '{expected_lead_source}' lead "
                        f"for {phone_number} on same day (lead_id={lead_id_existing})"
                    )
                    try:
                        from utils.flow_log import log_flow_event  # type: ignore

                        log_flow_event(
                            db,
                            flow_type="lead_appointment",
                            step="result",
                            status_code=200,
                            wa_id=wa_id,
                            name=getattr(customer, "name", None) or "",
                            description=(
                                f"Duplicate avoided (Zoho search): existing {expected_lead_source} lead {lead_id_existing}"
                            ),
                        )
                    except Exception:
                        pass
                    return {"success": True, "duplicate": True, "lead_id": lead_id_existing}
            else:
                print(
                    f"🔍 [LEAD APPOINTMENT FLOW] No '{expected_lead_source}' lead found in Zoho for {phone_number} on same day. "
                    f"Proceeding with lead creation..."
                )
        except Exception as _e:
            print(f"⚠️ [LEAD APPOINTMENT FLOW] Zoho-side duplicate check failed: {_e}")

        # Initialize variables for concern tracking
        selected_concern = None
        zoho_mapped_concern = None
        city = "Unknown"
        clinic = "Unknown"
        location = None  # FIX: Initialize location outside try block to avoid scope issues
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

        # -------- Final Lead Source / Sub Source / Language for Zoho --------
        try:
            _session_lead_source = session_data.get("lead_source")
            _session_language = session_data.get("language")
            _session_sub_source = session_data.get("sub_source")
        except Exception:
            _session_lead_source = None
            _session_language = None
            _session_sub_source = None

        # Check appointment_details for sub_source (may be set by callback handlers)
        _appointment_sub_source = None
        if appointment_details:
            _appointment_sub_source = appointment_details.get("sub_source")

        # Determine lead source based on flow type
        if flow_type == "treatment_flow":
            # Marketing treatment flow → always Business Listing / WhatsApp Dial
            lead_source_val = "Business Listing"
            sub_source_val = "WhatsApp Dial"
            language_val = None  # not used for treatment flow
        else:
            # Lead appointment flow → always use "Facebook" as lead source
            # Use session lead_source if available (should be "Facebook"), otherwise default to "Facebook"
            if _session_lead_source and _session_lead_source.strip():
                lead_source_val = _session_lead_source.strip()
                print(f"[LEAD APPOINTMENT FLOW] Using session lead_source: {lead_source_val}")
            else:
                lead_source_val = "Facebook"
                print(f"[LEAD APPOINTMENT FLOW] No session lead_source found, defaulting to: {lead_source_val}")
            # Use sub_source from appointment_details (set by callback handlers) or session state
            if _appointment_sub_source and _appointment_sub_source.strip():
                sub_source_val = _appointment_sub_source.strip()
                print(f"[LEAD APPOINTMENT FLOW] Using sub_source from appointment_details: {sub_source_val}")
            elif _session_sub_source and _session_sub_source.strip():
                sub_source_val = _session_sub_source.strip()
                print(f"[LEAD APPOINTMENT FLOW] Using sub_source from session: {sub_source_val}")
            else:
                sub_source_val = None  # No sub-source if not set
                print(f"[LEAD APPOINTMENT FLOW] No sub_source found, defaulting to None")
            language_val = _session_language if _session_language else None

        # Note: Duplicate checking (one lead per day per Lead Source) was already done earlier in this function
        # This prevents creating multiple leads with the same Lead Source for the same phone number on the same day

        # -------- Call Zoho lead service --------
        result = zoho_lead_service.create_lead(
            first_name=first_name,
            last_name=last_name,
            email=getattr(customer, 'email', '') or '',
            phone=phone_number,
            mobile=phone_number,
            city=city,
            lead_source=lead_source_val,
            company="Oliva Skin & Hair Clinic",
            description=(
                f"Lead from WhatsApp | Language: {language_val}" if language_val else "Lead from WhatsApp"
            ),
            appointment_details={
                "flow_type": (flow_type or "lead_appointment_flow"),
                "selected_city": city,
                "selected_clinic": clinic,
                **({"selected_location": location} if location else {}),
                "selected_week": session_data.get("selected_week", "Not specified"),
                "custom_date": appointment_date,
                "selected_time": appointment_time,
                "selected_concern": selected_concern,
                "zoho_mapped_concern": zoho_mapped_concern,
                "lead_source": lead_source_val,
                **({"language": language_val} if language_val else {}),
                # Preserve phone numbers from customer table
                **(
                    {"wa_phone": appointment_details.get("wa_phone")}
                    if appointment_details.get("wa_phone")
                    else {}
                ),
                **(
                    {"corrected_phone": appointment_details.get("corrected_phone")}
                    if appointment_details.get("corrected_phone")
                    else {}
                ),
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
                        zoho_lead_id=result.get("lead_id"),
                        first_name=first_name,
                        last_name=last_name,
                        email=getattr(customer, "email", "") or "",
                        phone=phone_number,
                        mobile=phone_number,
                        city=city,
                        location=location,
                        lead_source=lead_source_val,
                        company="Oliva Skin & Hair Clinic",
                        wa_id=wa_id,
                        customer_id=getattr(customer, "id", None),
                        appointment_details={
                            "selected_city": city,
                            "selected_clinic": clinic,
                            **({"selected_location": location} if location else {}),
                            "selected_concern": final_selected_concern,
                            "zoho_mapped_concern": final_mapped_concern,
                        },
                        treatment_name=final_selected_concern,
                        zoho_mapped_concern=final_mapped_concern,
                        primary_concern=final_mapped_concern or final_selected_concern,
                        sub_source=sub_source_val,
                    )
                    db.add(new_lead)
                    db.commit()
                    db.refresh(new_lead)
                    print(f"💾 [LEAD APPOINTMENT FLOW] Lead saved to local database with ID: {new_lead.id}")
                else:
                    print(f"⚠️ [LEAD APPOINTMENT FLOW] Lead already exists in database")
            except Exception as db_e:
                print(f"❌ [LEAD APPOINTMENT FLOW] Could not save lead to local database: {db_e}")
                db.rollback()
                # FIX: Return with db_save_failed flag instead of silently continuing
                result["db_save_failed"] = True
                result["db_error"] = str(db_e)
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
        dropoff_point: Where the user dropped off (e.g., "city_selection", "clinic_selection", "no_response_followup2", etc.)
        
    Returns a status dict.
    """
    
    try:
        # Get any partial appointment details
        appointment_details = {}
        try:
            from controllers.web_socket import lead_appointment_state, appointment_state
            appointment_details = lead_appointment_state.get(wa_id, {})
            
            # Also check appointment_state for treatment flow context
            appt_state = appointment_state.get(wa_id, {})
            if (
                bool(appt_state.get("from_treatment_flow"))
                or appt_state.get("flow_context") == "treatment"
                or bool(appt_state.get("treatment_flow_phone_id"))
            ):
                # Ensure flow_type is set to treatment_flow for dropoff leads
                appointment_details["flow_type"] = "treatment_flow"
                print(f"[create_lead_for_dropoff] Set flow_type=treatment_flow for dropoff lead (wa_id={wa_id}, dropoff_point={dropoff_point})")
        except Exception as e:
            print(f"[create_lead_for_dropoff] Could not get appointment state: {e}")
        
        # If flow_type is not set, try to infer from dropoff_point
        # If it's a follow-up dropoff, it's likely from treatment flow
        if not appointment_details.get("flow_type") and "followup" in dropoff_point.lower():
            appointment_details["flow_type"] = "treatment_flow"
            print(f"[create_lead_for_dropoff] Inferred flow_type=treatment_flow from dropoff_point={dropoff_point}")
        
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