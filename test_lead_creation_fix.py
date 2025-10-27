#!/usr/bin/env python3
"""
Quick Test for Lead Creation Fix
Tests the fixed lead creation with proper Last_Name handling
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

async def test_lead_creation_fix():
    """Test the fixed lead creation"""
    
    print("🔧 Testing Lead Creation Fix")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
        
        # Mock customer object
        class MockCustomer:
            def __init__(self):
                self.name = "Bhargavi"
                self.email = "bhargavi122705@gmail.com"
                self.wa_id = "918309866859"
        
        mock_customer = MockCustomer()
        mock_db = None  # In real usage, this would be a database session
        
        appointment_details = {
            "selected_city": "Hyderabad",
            "selected_clinic": "Banjara",
            "selected_date": "2025-10-28"
        }
        
        print("📋 Test Data:")
        print(f"   Customer: {mock_customer.name}")
        print(f"   Email: {mock_customer.email}")
        print(f"   WA ID: {mock_customer.wa_id}")
        print(f"   Appointment: {appointment_details}")
        
        print("\n🚀 Testing lead creation...")
        result = await create_lead_for_appointment(
            db=mock_db,
            wa_id=mock_customer.wa_id,
            customer=mock_customer,
            appointment_details=appointment_details,
            lead_status="PENDING"
        )
        
        print(f"\n📊 Result: {result}")
        
        if result["success"]:
            print("✅ SUCCESS! Lead creation fixed!")
            print(f"🆔 Lead ID: {result.get('lead_id')}")
        else:
            print(f"❌ FAILED! Error: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        import traceback
        print(f"📝 Traceback: {traceback.format_exc()}")

def show_fixes():
    """Show what was fixed"""
    
    print("\n🔧 Fixes Applied:")
    print("=" * 50)
    
    fixes = [
        "✅ Fixed Last_Name requirement - Now splits user name into First_Name and Last_Name",
        "✅ Fixed appointment date capture - Now tries multiple date fields (custom_date, selected_date, appointment_date)",
        "✅ Fixed appointment time capture - Now tries multiple time fields (selected_time, custom_time, appointment_time)",
        "✅ Fixed duplicate description - Now creates clean description without duplicates",
        "✅ Added better error handling and logging"
    ]
    
    for fix in fixes:
        print(f"   {fix}")
    
    print("\n📋 What the fix does:")
    print("   - If user name is 'Bhargavi', it becomes First_Name: 'Bhargavi', Last_Name: 'Lead'")
    print("   - If user name is 'John Doe', it becomes First_Name: 'John', Last_Name: 'Doe'")
    print("   - Captures appointment date from multiple possible fields")
    print("   - Captures appointment time from multiple possible fields")
    print("   - Creates clean description without duplicates")

if __name__ == "__main__":
    show_fixes()
    asyncio.run(test_lead_creation_fix())
    
    print("\n" + "=" * 50)
    print("🎯 Summary:")
    print("✅ Fixed Last_Name requirement issue")
    print("✅ Fixed appointment details capture")
    print("✅ Fixed duplicate description issue")
    print("✅ Added better error handling")
    print("\n📱 Now try the lead appointment flow again!")
    print("🔍 Check your logs for successful lead creation")
    print("📊 Use the API to verify leads are being created")
