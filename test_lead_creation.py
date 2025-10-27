#!/usr/bin/env python3
"""
Test Zoho Lead Creation
This will create a test lead to verify the integration works
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def test_lead_creation():
    """Test creating a lead in Zoho CRM"""
    
    print("📝 Testing Zoho Lead Creation...")
    print("=" * 50)
    
    load_dotenv()
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_service import ZohoLeadService
        
        service = ZohoLeadService()
        
        # Test data
        test_data = {
            "first_name": "Test",
            "last_name": "Integration",
            "email": "test.integration@example.com",
            "phone": "919876543210",
            "mobile": "919876543210", 
            "city": "Delhi",
            "lead_source": "WhatsApp Lead-to-Appointment Flow",
            "lead_status": "PENDING",
            "company": "Oliva Skin & Hair Clinic",
            "description": f"Test lead created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "appointment_details": {
                "selected_city": "Delhi",
                "selected_clinic": "Main Branch",
                "custom_date": "2024-01-15",
                "selected_time": "10:00 AM"
            }
        }
        
        print("📋 Test Lead Data:")
        print(json.dumps(test_data, indent=2))
        
        print("\n🚀 Creating lead...")
        result = service.create_lead(**test_data)
        
        print("\n📊 Result:")
        print(json.dumps(result, indent=2))
        
        if result["success"]:
            print(f"\n🎉 SUCCESS! Lead created with ID: {result.get('lead_id')}")
            print("✅ Integration is working!")
            print(f"🔗 Check your Zoho CRM for lead ID: {result.get('lead_id')}")
        else:
            print(f"\n❌ FAILED! Error: {result.get('error')}")
            print("🔧 Check the error message above for troubleshooting")
            
    except Exception as e:
        print(f"❌ Exception during test: {str(e)}")
        import traceback
        print(f"📝 Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_lead_creation()
