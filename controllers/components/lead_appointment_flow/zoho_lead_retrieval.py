"""
Zoho Lead Retrieval API for WhatsApp Source Leads
Provides endpoints to get leads created through WhatsApp Lead-to-Appointment Flow
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import requests
import json

from sqlalchemy.orm import Session
from utils.zoho_auth import get_valid_access_token


class ZohoLeadRetrievalService:
    """Service class for retrieving Zoho CRM leads"""
    
    def __init__(self):
        self.base_url = "https://www.zohoapis.in/crm/v2.1/Leads"
        self.access_token = None
    
    def _get_access_token(self) -> str:
        """Get valid access token for Zoho API"""
        if not self.access_token:
            self.access_token = get_valid_access_token()
        return self.access_token
    
    def get_whatsapp_leads(
        self,
        *,
        limit: int = 200,
        page: int = 1,
        sort_order: str = "desc",
        sort_by: str = "Created_Time",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        lead_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get leads created through WhatsApp Lead-to-Appointment Flow
        
        Args:
            limit: Number of records to return (max 200)
            page: Page number for pagination
            sort_order: 'asc' or 'desc'
            sort_by: Field to sort by (e.g., 'Created_Time', 'Modified_Time')
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format
            lead_status: Filter by lead status (e.g., 'CALL_INITIATED', 'PENDING', 'NO_CALLBACK')
            
        Returns:
            Dict containing leads data and metadata
        """
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            print(f"\n📥 [ZOHO LEAD RETRIEVAL] Starting at {timestamp}")
            print(f"🔍 [ZOHO LEAD RETRIEVAL] Getting WhatsApp source leads")
            print(f"📊 [ZOHO LEAD RETRIEVAL] Limit: {limit}, Page: {page}")
            print(f"📅 [ZOHO LEAD RETRIEVAL] Date range: {date_from} to {date_to}")
            print(f"📋 [ZOHO LEAD RETRIEVAL] Lead status filter: {lead_status}")
            
            access_token = self._get_access_token()
            if not access_token:
                print(f"❌ [ZOHO LEAD RETRIEVAL] FAILED - No access token available")
                return {"success": False, "error": "no_access_token"}
            
            print(f"✅ [ZOHO LEAD RETRIEVAL] Access token obtained: {access_token[:20]}...")
            
            # Build query parameters
            params = {
                "limit": limit,
                "page": page,
                "sort_order": sort_order,
                "sort_by": sort_by
            }
            
            # Add date filters if provided
            if date_from:
                params["created_time"] = f"{date_from}T00:00:00+05:30"
            if date_to:
                if "created_time" in params:
                    params["created_time"] = f"{date_from}T00:00:00+05:30,{date_to}T23:59:59+05:30"
                else:
                    params["created_time"] = f"{date_to}T23:59:59+05:30"
            
            # Build the query string for WhatsApp source leads
            query_conditions = ["Lead_Source:equals:WhatsApp Lead-to-Appointment Flow"]
            
            # Add lead status filter if provided
            if lead_status:
                query_conditions.append(f"Lead_Status:equals:{lead_status}")
            
            # Combine query conditions
            query_string = " and ".join(query_conditions)
            params["criteria"] = f"({query_string})"
            
            print(f"🔍 [ZOHO LEAD RETRIEVAL] Query: {query_string}")
            
            # Prepare headers
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            }
            
            print(f"🌐 [ZOHO LEAD RETRIEVAL] Making API call to: {self.base_url}")
            print(f"📡 [ZOHO LEAD RETRIEVAL] Headers: Authorization=Zoho-oauthtoken {access_token[:20]}...")
            print(f"📋 [ZOHO LEAD RETRIEVAL] Parameters: {params}")
            
            # Make API call
            response = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=30
            )
            
            print(f"📊 [ZOHO LEAD RETRIEVAL] API Response Status: {response.status_code}")
            print(f"📄 [ZOHO LEAD RETRIEVAL] API Response Body: {response.text}")
            
            # If token invalid/expired, refresh and retry once
            if response.status_code == 401:
                try:
                    body_lower = (response.text or "").lower()
                except Exception:
                    body_lower = ""
                if "invalid_token" in body_lower or "invalid oauth token" in body_lower or "invalid_oauth_token" in body_lower:
                    print("⚠️  [ZOHO LEAD RETRIEVAL] Detected INVALID_TOKEN (401). Refreshing token and retrying once...")
                    self.access_token = get_valid_access_token()
                    refreshed = self.access_token
                    print(f"✅ [ZOHO LEAD RETRIEVAL] New access token obtained: {refreshed[:20]}...")
                    headers_retry = {
                        **headers,
                        "Authorization": f"Zoho-oauthtoken {refreshed}"
                    }
                    response = requests.get(
                        self.base_url,
                        headers=headers_retry,
                        params=params,
                        timeout=30
                    )
                    print(f"🔁 [ZOHO LEAD RETRIEVAL] Retry Response Status: {response.status_code}")
                    print(f"🧾 [ZOHO LEAD RETRIEVAL] Retry Response Body: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                leads = response_data.get("data", [])
                info = response_data.get("info", {})
                
                print(f"✅ [ZOHO LEAD RETRIEVAL] SUCCESS!")
                print(f"📊 [ZOHO LEAD RETRIEVAL] Found {len(leads)} leads")
                print(f"📈 [ZOHO LEAD RETRIEVAL] Total records: {info.get('count', 'Unknown')}")
                print(f"📄 [ZOHO LEAD RETRIEVAL] Page info: {info}")
                
                # Process and enhance lead data
                processed_leads = self._process_lead_data(leads)
                
                return {
                    "success": True,
                    "leads": processed_leads,
                    "total_count": info.get("count", len(leads)),
                    "page_info": info,
                    "query_info": {
                        "limit": limit,
                        "page": page,
                        "sort_order": sort_order,
                        "sort_by": sort_by,
                        "date_from": date_from,
                        "date_to": date_to,
                        "lead_status": lead_status,
                        "query": query_string
                    }
                }
            else:
                error_msg = f"API Error {response.status_code}: {response.text}"
                print(f"❌ [ZOHO LEAD RETRIEVAL] FAILED!")
                print(f"🚨 [ZOHO LEAD RETRIEVAL] Error: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            print(f"❌ [ZOHO LEAD RETRIEVAL] EXCEPTION!")
            print(f"🚨 [ZOHO LEAD RETRIEVAL] Exception: {error_msg}")
            import traceback
            print(f"📝 [ZOHO LEAD RETRIEVAL] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": error_msg}
    
    def _process_lead_data(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process and enhance lead data for better readability"""
        
        processed_leads = []
        
        for lead in leads:
            processed_lead = {
                "id": lead.get("id"),
                "first_name": lead.get("First_Name", ""),
                "last_name": lead.get("Last_Name", ""),
                "full_name": f"{lead.get('First_Name', '')} {lead.get('Last_Name', '')}".strip(),
                "email": lead.get("Email", ""),
                "phone": lead.get("Phone", ""),
                "mobile": lead.get("Mobile", ""),
                "city": lead.get("City", ""),
                "company": lead.get("Company", ""),
                "lead_source": lead.get("Lead_Source", ""),
                "lead_status": lead.get("Lead_Status", ""),
                "description": lead.get("Description", ""),
                "created_time": lead.get("Created_Time", ""),
                "modified_time": lead.get("Modified_Time", ""),
                "created_by": lead.get("Created_By", {}).get("name", ""),
                "modified_by": lead.get("Modified_By", {}).get("name", ""),
                "raw_data": lead  # Keep original data for reference
            }
            
            # Extract appointment details from description
            appointment_details = self._extract_appointment_details(lead.get("Description", ""))
            processed_lead["appointment_details"] = appointment_details
            
            processed_leads.append(processed_lead)
        
        return processed_leads
    
    def _extract_appointment_details(self, description: str) -> Dict[str, str]:
        """Extract appointment details from lead description"""
        
        details = {
            "city": "Unknown",
            "clinic": "Unknown", 
            "preferred_date": "Not specified",
            "preferred_time": "Not specified",
            "status": "Unknown",
            "preference": ""
        }
        
        if not description:
            return details
        
        # Parse description for appointment details
        parts = description.split(" | ")
        
        for part in parts:
            if part.startswith("City:"):
                details["city"] = part.replace("City:", "").strip()
            elif part.startswith("Clinic:"):
                details["clinic"] = part.replace("Clinic:", "").strip()
            elif part.startswith("Preferred Date:"):
                details["preferred_date"] = part.replace("Preferred Date:", "").strip()
            elif part.startswith("Preferred Time:"):
                details["preferred_time"] = part.replace("Preferred Time:", "").strip()
            elif part.startswith("Status:"):
                details["status"] = part.replace("Status:", "").strip()
            elif part.startswith("Preference:"):
                details["preference"] = part.replace("Preference:", "").strip()
        
        return details
    
    def get_lead_by_id(self, lead_id: str) -> Dict[str, Any]:
        """Get a specific lead by ID"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            print(f"\n🔍 [ZOHO LEAD BY ID] Starting at {timestamp}")
            print(f"🆔 [ZOHO LEAD BY ID] Lead ID: {lead_id}")
            
            access_token = self._get_access_token()
            if not access_token:
                print(f"❌ [ZOHO LEAD BY ID] FAILED - No access token available")
                return {"success": False, "error": "no_access_token"}
            
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            }
            
            url = f"{self.base_url}/{lead_id}"
            
            print(f"🌐 [ZOHO LEAD BY ID] Making API call to: {url}")
            
            response = requests.get(url, headers=headers, timeout=30)
            
            print(f"📊 [ZOHO LEAD BY ID] API Response Status: {response.status_code}")
            
            # If token invalid/expired, refresh and retry once
            if response.status_code == 401:
                try:
                    body_lower = (response.text or "").lower()
                except Exception:
                    body_lower = ""
                if "invalid_token" in body_lower or "invalid oauth token" in body_lower or "invalid_oauth_token" in body_lower:
                    print("⚠️  [ZOHO LEAD BY ID] Detected INVALID_TOKEN (401). Refreshing token and retrying once...")
                    self.access_token = get_valid_access_token()
                    refreshed = self.access_token
                    print(f"✅ [ZOHO LEAD BY ID] New access token obtained: {refreshed[:20]}...")
                    headers_retry = {
                        **headers,
                        "Authorization": f"Zoho-oauthtoken {refreshed}"
                    }
                    response = requests.get(url, headers=headers_retry, timeout=30)
                    print(f"🔁 [ZOHO LEAD BY ID] Retry Response Status: {response.status_code}")
                    print(f"🧾 [ZOHO LEAD BY ID] Retry Response Body: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                lead_data = response_data.get("data", [{}])[0]
                
                print(f"✅ [ZOHO LEAD BY ID] SUCCESS!")
                print(f"👤 [ZOHO LEAD BY ID] Lead: {lead_data.get('First_Name', '')} {lead_data.get('Last_Name', '')}")
                
                # Process the lead data
                processed_leads = self._process_lead_data([lead_data])
                
                return {
                    "success": True,
                    "lead": processed_leads[0] if processed_leads else None,
                    "raw_data": lead_data
                }
            else:
                error_msg = f"API Error {response.status_code}: {response.text}"
                print(f"❌ [ZOHO LEAD BY ID] FAILED!")
                print(f"🚨 [ZOHO LEAD BY ID] Error: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            print(f"❌ [ZOHO LEAD BY ID] EXCEPTION!")
            print(f"🚨 [ZOHO LEAD BY ID] Exception: {error_msg}")
            return {"success": False, "error": error_msg}
    
    def get_lead_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get statistics for WhatsApp leads over a specified period"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        
        try:
            print(f"\n📊 [LEAD STATISTICS] Starting at {timestamp}")
            print(f"📅 [LEAD STATISTICS] Period: {days} days ({date_from} to {date_to})")
            
            # Get all leads for the period
            result = self.get_whatsapp_leads(
                limit=200,
                date_from=date_from,
                date_to=date_to
            )
            
            if not result["success"]:
                return result
            
            leads = result["leads"]
            
            # Calculate statistics
            stats = {
                "total_leads": len(leads),
                "period_days": days,
                "date_from": date_from,
                "date_to": date_to,
                "status_breakdown": {},
                "city_breakdown": {},
                "daily_breakdown": {},
                "q5_events": 0,
                "termination_events": 0,
                "pending_leads": 0
            }
            
            # Analyze leads
            for lead in leads:
                # Status breakdown
                status = lead["lead_status"]
                stats["status_breakdown"][status] = stats["status_breakdown"].get(status, 0) + 1
                
                # City breakdown
                city = lead["appointment_details"]["city"]
                stats["city_breakdown"][city] = stats["city_breakdown"].get(city, 0) + 1
                
                # Count Q5 and termination events
                if status == "CALL_INITIATED":
                    stats["q5_events"] += 1
                elif status == "NO_CALLBACK":
                    stats["termination_events"] += 1
                elif status == "PENDING":
                    stats["pending_leads"] += 1
                
                # Daily breakdown
                if lead["created_time"]:
                    try:
                        created_date = datetime.fromisoformat(lead["created_time"].replace("Z", "+00:00")).strftime("%Y-%m-%d")
                        stats["daily_breakdown"][created_date] = stats["daily_breakdown"].get(created_date, 0) + 1
                    except:
                        pass
            
            print(f"✅ [LEAD STATISTICS] SUCCESS!")
            print(f"📊 [LEAD STATISTICS] Total leads: {stats['total_leads']}")
            print(f"📞 [LEAD STATISTICS] Q5 events: {stats['q5_events']}")
            print(f"🔄 [LEAD STATISTICS] Termination events: {stats['termination_events']}")
            print(f"⏳ [LEAD STATISTICS] Pending leads: {stats['pending_leads']}")
            
            return {
                "success": True,
                "statistics": stats,
                "leads": leads
            }
            
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            print(f"❌ [LEAD STATISTICS] EXCEPTION!")
            print(f"🚨 [LEAD STATISTICS] Exception: {error_msg}")
            return {"success": False, "error": error_msg}


# Global service instance
zoho_lead_retrieval_service = ZohoLeadRetrievalService()


# Convenience functions for easy use
async def get_whatsapp_leads(
    limit: int = 200,
    page: int = 1,
    sort_order: str = "desc",
    sort_by: str = "Created_Time",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    lead_status: Optional[str] = None
) -> Dict[str, Any]:
    """Get leads created through WhatsApp Lead-to-Appointment Flow"""
    return zoho_lead_retrieval_service.get_whatsapp_leads(
        limit=limit,
        page=page,
        sort_order=sort_order,
        sort_by=sort_by,
        date_from=date_from,
        date_to=date_to,
        lead_status=lead_status
    )


async def get_lead_by_id(lead_id: str) -> Dict[str, Any]:
    """Get a specific lead by ID"""
    return zoho_lead_retrieval_service.get_lead_by_id(lead_id)


async def get_lead_statistics(days: int = 30) -> Dict[str, Any]:
    """Get statistics for WhatsApp leads"""
    return zoho_lead_retrieval_service.get_lead_statistics(days)
