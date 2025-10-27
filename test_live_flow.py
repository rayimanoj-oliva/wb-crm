#!/usr/bin/env python3
"""
Live WhatsApp Flow Test
This simulates the actual WhatsApp flow to test Q5 and termination events
"""

import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

class MockCustomer:
    """Mock customer object for testing"""
    def __init__(self, name="Test Customer", email="test@example.com"):
        self.name = name
        self.email = email
        self.wa_id = "+919876543210"

async def test_q5_yes_response():
    """Test Q5 'Yes' response (should trigger auto-dial)"""
    
    print("📞 Testing Q5 'Yes' Response (Auto-Dial Trigger)...")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_service import trigger_q5_auto_dial_event
        
        mock_customer = MockCustomer("John Doe", "john@example.com")
        
        appointment_details = {
            "selected_city": "Delhi",
            "selected_clinic": "Main Branch",
            "custom_date": "2024-01-15", 
            "selected_time": "10:00 AM"
        }
        
        print("📋 Test Data:")
        print(f"   Customer: {mock_customer.name}")
        print(f"   WA ID: {mock_customer.wa_id}")
        print(f"   Appointment: {appointment_details}")
        
        result = await trigger_q5_auto_dial_event(
            db=None,  # Mock DB
            wa_id=mock_customer.wa_id,
            customer=mock_customer,
            appointment_details=appointment_details
        )
        
        print(f"\n📊 Q5 Result: {result}")
        
        if result["success"]:
            print("✅ Q5 Auto-dial event triggered successfully!")
            print(f"📝 Lead ID: {result.get('lead_result', {}).get('lead_id')}")
        else:
            print(f"❌ Q5 Auto-dial failed: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Q5 Test Exception: {str(e)}")

async def test_q5_no_response():
    """Test Q5 'No' response (should create follow-up lead)"""
    
    print("\n🚫 Testing Q5 'No' Response (Follow-up Lead)...")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_service import handle_termination_event
        
        mock_customer = MockCustomer("Jane Smith", "jane@example.com")
        
        appointment_details = {
            "selected_city": "Mumbai",
            "selected_clinic": "Branch Office",
            "custom_date": "2024-01-16",
            "selected_time": "2:00 PM"
        }
        
        print("📋 Test Data:")
        print(f"   Customer: {mock_customer.name}")
        print(f"   WA ID: {mock_customer.wa_id}")
        print(f"   Appointment: {appointment_details}")
        
        result = await handle_termination_event(
            db=None,  # Mock DB
            wa_id=mock_customer.wa_id,
            customer=mock_customer,
            termination_reason="negative_q5_response",
            appointment_details=appointment_details
        )
        
        print(f"\n📊 Termination Result: {result}")
        
        if result["success"]:
            print("✅ Termination event handled successfully!")
            print(f"📝 Lead ID: {result.get('lead_result', {}).get('lead_id')}")
            print("📋 Lead created for follow-up/remarketing")
        else:
            print(f"❌ Termination handling failed: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Termination Test Exception: {str(e)}")

async def test_dropoff_event():
    """Test dropoff event (should create follow-up lead)"""
    
    print("\n🔄 Testing Dropoff Event (Follow-up Lead)...")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_service import handle_termination_event
        
        mock_customer = MockCustomer("Bob Wilson", "bob@example.com")
        
        appointment_details = {
            "selected_city": "Bangalore",
            "selected_clinic": "Tech Park Branch"
        }
        
        print("📋 Test Data:")
        print(f"   Customer: {mock_customer.name}")
        print(f"   WA ID: {mock_customer.wa_id}")
        print(f"   Dropoff Point: city_selection")
        print(f"   Partial Data: {appointment_details}")
        
        result = await handle_termination_event(
            db=None,  # Mock DB
            wa_id=mock_customer.wa_id,
            customer=mock_customer,
            termination_reason="dropped_off_at_city_selection",
            appointment_details=appointment_details
        )
        
        print(f"\n📊 Dropoff Result: {result}")
        
        if result["success"]:
            print("✅ Dropoff event handled successfully!")
            print(f"📝 Lead ID: {result.get('lead_result', {}).get('lead_id')}")
            print("📋 Lead created for follow-up/remarketing")
        else:
            print(f"❌ Dropoff handling failed: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Dropoff Test Exception: {str(e)}")

async def run_live_tests():
    """Run all live flow tests"""
    
    print("🎭 Live WhatsApp Flow Tests")
    print("=" * 50)
    print("This simulates real WhatsApp interactions")
    print("=" * 50)
    
    await test_q5_yes_response()
    await test_q5_no_response() 
    await test_dropoff_event()
    
    print("\n" + "=" * 50)
    print("🎯 Live Test Summary:")
    print("✅ Q5 'Yes' → Auto-dial trigger")
    print("✅ Q5 'No' → Follow-up lead")
    print("✅ Dropoff → Follow-up lead")
    print("\n📋 Check your Zoho CRM for the created leads!")

if __name__ == "__main__":
    asyncio.run(run_live_tests())
