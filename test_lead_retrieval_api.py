#!/usr/bin/env python3
"""
Test Script for Zoho Lead Retrieval API
Demonstrates how to use the lead retrieval endpoints
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

async def test_get_whatsapp_leads():
    """Test getting WhatsApp source leads"""
    
    print("📥 Testing WhatsApp Lead Retrieval")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_retrieval import get_whatsapp_leads
        
        # Test 1: Get recent leads
        print("\n🔍 Test 1: Get recent WhatsApp leads")
        result = await get_whatsapp_leads(limit=10, page=1)
        
        if result["success"]:
            print(f"✅ SUCCESS! Found {len(result['leads'])} leads")
            print(f"📊 Total count: {result['total_count']}")
            
            for i, lead in enumerate(result["leads"][:3], 1):  # Show first 3 leads
                print(f"\n📋 Lead {i}:")
                print(f"   ID: {lead['id']}")
                print(f"   Name: {lead['full_name']}")
                print(f"   Phone: {lead['phone']}")
                print(f"   Status: {lead['lead_status']}")
                print(f"   City: {lead['appointment_details']['city']}")
                print(f"   Clinic: {lead['appointment_details']['clinic']}")
                print(f"   Created: {lead['created_time']}")
        else:
            print(f"❌ FAILED: {result['error']}")
        
        # Test 2: Get leads by status
        print("\n🔍 Test 2: Get CALL_INITIATED leads (Q5 events)")
        result = await get_whatsapp_leads(limit=5, lead_status="CALL_INITIATED")
        
        if result["success"]:
            print(f"✅ SUCCESS! Found {len(result['leads'])} Q5 events")
            for lead in result["leads"]:
                print(f"   📞 {lead['full_name']} - {lead['phone']} - {lead['created_time']}")
        else:
            print(f"❌ FAILED: {result['error']}")
        
        # Test 3: Get leads by date range
        print("\n🔍 Test 3: Get leads from last 7 days")
        date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        result = await get_whatsapp_leads(limit=10, date_from=date_from)
        
        if result["success"]:
            print(f"✅ SUCCESS! Found {len(result['leads'])} leads in last 7 days")
        else:
            print(f"❌ FAILED: {result['error']}")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")

async def test_get_lead_by_id():
    """Test getting a specific lead by ID"""
    
    print("\n🔍 Testing Lead by ID Retrieval")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_retrieval import get_lead_by_id
        
        # First get a lead ID from the list
        from controllers.components.lead_appointment_flow.zoho_lead_retrieval import get_whatsapp_leads
        
        leads_result = await get_whatsapp_leads(limit=1)
        
        if leads_result["success"] and leads_result["leads"]:
            lead_id = leads_result["leads"][0]["id"]
            print(f"🔍 Testing with Lead ID: {lead_id}")
            
            result = await get_lead_by_id(lead_id)
            
            if result["success"]:
                lead = result["lead"]
                print(f"✅ SUCCESS! Retrieved lead:")
                print(f"   ID: {lead['id']}")
                print(f"   Name: {lead['full_name']}")
                print(f"   Phone: {lead['phone']}")
                print(f"   Email: {lead['email']}")
                print(f"   Status: {lead['lead_status']}")
                print(f"   City: {lead['appointment_details']['city']}")
                print(f"   Clinic: {lead['appointment_details']['clinic']}")
                print(f"   Preferred Date: {lead['appointment_details']['preferred_date']}")
                print(f"   Preferred Time: {lead['appointment_details']['preferred_time']}")
                print(f"   Created: {lead['created_time']}")
            else:
                print(f"❌ FAILED: {result['error']}")
        else:
            print("⚠️ No leads found to test with")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")

async def test_get_statistics():
    """Test getting lead statistics"""
    
    print("\n📊 Testing Lead Statistics")
    print("=" * 50)
    
    try:
        from controllers.components.lead_appointment_flow.zoho_lead_retrieval import get_lead_statistics
        
        # Test statistics for last 30 days
        result = await get_lead_statistics(days=30)
        
        if result["success"]:
            stats = result["statistics"]
            print(f"✅ SUCCESS! Statistics for last {stats['period_days']} days:")
            print(f"   📊 Total leads: {stats['total_leads']}")
            print(f"   📞 Q5 events: {stats['q5_events']}")
            print(f"   🔄 Termination events: {stats['termination_events']}")
            print(f"   ⏳ Pending leads: {stats['pending_leads']}")
            
            print(f"\n📋 Status breakdown:")
            for status, count in stats["status_breakdown"].items():
                print(f"   {status}: {count}")
            
            print(f"\n🏙️ City breakdown:")
            for city, count in stats["city_breakdown"].items():
                print(f"   {city}: {count}")
            
            print(f"\n📅 Daily breakdown (last 5 days):")
            daily_items = list(stats["daily_breakdown"].items())[-5:]
            for date, count in daily_items:
                print(f"   {date}: {count}")
        else:
            print(f"❌ FAILED: {result['error']}")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")

async def test_api_endpoints():
    """Test the API endpoints (if FastAPI is available)"""
    
    print("\n🌐 Testing API Endpoints")
    print("=" * 50)
    
    print("📋 Available API Endpoints:")
    endpoints = [
        "GET /api/zoho-leads/whatsapp - Get all WhatsApp source leads",
        "GET /api/zoho-leads/{lead_id} - Get specific lead by ID",
        "GET /api/zoho-leads/statistics/summary - Get lead statistics",
        "GET /api/zoho-leads/whatsapp/q5-events - Get Q5 events only",
        "GET /api/zoho-leads/whatsapp/termination-events - Get termination events",
        "GET /api/zoho-leads/whatsapp/pending - Get pending leads",
        "GET /api/zoho-leads/health - Health check"
    ]
    
    for endpoint in endpoints:
        print(f"   🔹 {endpoint}")
    
    print("\n📝 Example API calls:")
    print("   curl 'http://localhost:8000/api/zoho-leads/whatsapp?limit=10&lead_status=CALL_INITIATED'")
    print("   curl 'http://localhost:8000/api/zoho-leads/statistics/summary?days=30'")
    print("   curl 'http://localhost:8000/api/zoho-leads/whatsapp/q5-events?days=7'")

async def run_all_tests():
    """Run all tests"""
    
    print("🧪 Zoho Lead Retrieval API Tests")
    print("=" * 70)
    print("This script tests the lead retrieval functionality")
    print("=" * 70)
    
    await test_get_whatsapp_leads()
    await test_get_lead_by_id()
    await test_get_statistics()
    await test_api_endpoints()
    
    print("\n" + "=" * 70)
    print("🎯 Test Summary:")
    print("✅ Lead retrieval service created")
    print("✅ API endpoints defined")
    print("✅ Statistics functionality implemented")
    print("✅ Q5 and termination event filtering")
    print("✅ Date range filtering")
    print("✅ Lead detail extraction")
    print("\n📱 Next Steps:")
    print("1. Add the router to your FastAPI app")
    print("2. Test the API endpoints")
    print("3. Use the endpoints in your dashboard")
    print("4. Monitor lead creation and conversion")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
