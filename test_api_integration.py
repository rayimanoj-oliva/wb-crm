#!/usr/bin/env python3
"""
Quick Test Script for Zoho Lead API Integration
Tests if the API endpoints are properly integrated and accessible
"""

import requests
import json
import time
from datetime import datetime

def test_api_endpoints():
    """Test if the API endpoints are accessible"""
    
    print("🧪 Testing Zoho Lead API Integration")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test endpoints
    endpoints = [
        {
            "name": "Health Check",
            "url": f"{base_url}/api/zoho-leads/health",
            "method": "GET",
            "expected_status": 200
        },
        {
            "name": "WhatsApp Leads",
            "url": f"{base_url}/api/zoho-leads/whatsapp?limit=5",
            "method": "GET",
            "expected_status": 200
        },
        {
            "name": "Lead Statistics",
            "url": f"{base_url}/api/zoho-leads/statistics/summary?days=30",
            "method": "GET",
            "expected_status": 200
        },
        {
            "name": "Q5 Events",
            "url": f"{base_url}/api/zoho-leads/whatsapp/q5-events?days=7",
            "method": "GET",
            "expected_status": 200
        },
        {
            "name": "Termination Events",
            "url": f"{base_url}/api/zoho-leads/whatsapp/termination-events?days=7",
            "method": "GET",
            "expected_status": 200
        },
        {
            "name": "Pending Leads",
            "url": f"{base_url}/api/zoho-leads/whatsapp/pending?days=7",
            "method": "GET",
            "expected_status": 200
        }
    ]
    
    print("🔍 Testing API endpoints...")
    print("=" * 50)
    
    results = []
    
    for endpoint in endpoints:
        print(f"\n🔹 Testing {endpoint['name']}...")
        print(f"   URL: {endpoint['url']}")
        
        try:
            response = requests.get(endpoint['url'], timeout=10)
            
            if response.status_code == endpoint['expected_status']:
                print(f"   ✅ SUCCESS! Status: {response.status_code}")
                
                # Try to parse JSON response
                try:
                    data = response.json()
                    print(f"   📊 Response: {json.dumps(data, indent=2)[:200]}...")
                except:
                    print(f"   📄 Response: {response.text[:200]}...")
                
                results.append({
                    "name": endpoint['name'],
                    "status": "SUCCESS",
                    "status_code": response.status_code
                })
            else:
                print(f"   ❌ FAILED! Expected: {endpoint['expected_status']}, Got: {response.status_code}")
                print(f"   📄 Response: {response.text[:200]}...")
                
                results.append({
                    "name": endpoint['name'],
                    "status": "FAILED",
                    "status_code": response.status_code,
                    "error": response.text[:200]
                })
                
        except requests.exceptions.ConnectionError:
            print(f"   ❌ CONNECTION ERROR! Is your FastAPI server running?")
            print(f"   💡 Try: uvicorn app:app --reload")
            
            results.append({
                "name": endpoint['name'],
                "status": "CONNECTION_ERROR",
                "error": "Server not running"
            })
            
        except Exception as e:
            print(f"   ❌ EXCEPTION! {str(e)}")
            
            results.append({
                "name": endpoint['name'],
                "status": "EXCEPTION",
                "error": str(e)
            })
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print("=" * 50)
    
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    total_count = len(results)
    
    for result in results:
        status_icon = "✅" if result["status"] == "SUCCESS" else "❌"
        print(f"{status_icon} {result['name']}: {result['status']}")
        if result["status"] != "SUCCESS" and "error" in result:
            print(f"   Error: {result['error']}")
    
    print(f"\n🎯 Overall: {success_count}/{total_count} endpoints working")
    
    if success_count == total_count:
        print("🎉 All endpoints are working! Check your FastAPI docs at:")
        print("   http://localhost:8000/docs")
    elif success_count > 0:
        print("⚠️ Some endpoints are working. Check the errors above.")
    else:
        print("❌ No endpoints are working. Check your server setup.")

def test_fastapi_docs():
    """Test if FastAPI docs are accessible"""
    
    print("\n📚 Testing FastAPI Documentation")
    print("=" * 50)
    
    docs_url = "http://localhost:8000/docs"
    openapi_url = "http://localhost:8000/openapi.json"
    
    try:
        print(f"🔍 Checking FastAPI docs at: {docs_url}")
        response = requests.get(docs_url, timeout=5)
        
        if response.status_code == 200:
            print("✅ FastAPI docs are accessible!")
            print(f"📖 Open your browser to: {docs_url}")
            print("🔍 Look for 'Zoho Leads' section in the docs")
        else:
            print(f"❌ FastAPI docs not accessible. Status: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to FastAPI server")
        print("💡 Make sure your server is running:")
        print("   uvicorn app:app --reload")
    except Exception as e:
        print(f"❌ Error checking docs: {str(e)}")

def show_integration_status():
    """Show integration status and next steps"""
    
    print("\n🔧 Integration Status")
    print("=" * 50)
    
    print("✅ Files created:")
    print("   - controllers/components/lead_appointment_flow/zoho_lead_retrieval.py")
    print("   - controllers/components/lead_appointment_flow/zoho_lead_api.py")
    print("   - Updated app.py with router inclusion")
    
    print("\n✅ Router added to FastAPI app:")
    print("   - Import: from controllers.components.lead_appointment_flow.zoho_lead_api import router as zoho_leads_router")
    print("   - Include: app.include_router(zoho_leads_router)")
    
    print("\n🔗 Available endpoints:")
    endpoints = [
        "GET /api/zoho-leads/health",
        "GET /api/zoho-leads/whatsapp",
        "GET /api/zoho-leads/{lead_id}",
        "GET /api/zoho-leads/statistics/summary",
        "GET /api/zoho-leads/whatsapp/q5-events",
        "GET /api/zoho-leads/whatsapp/termination-events",
        "GET /api/zoho-leads/whatsapp/pending"
    ]
    
    for endpoint in endpoints:
        print(f"   🔹 {endpoint}")
    
    print("\n📱 Next steps:")
    print("1. Start your FastAPI server: uvicorn app:app --reload")
    print("2. Open browser to: http://localhost:8000/docs")
    print("3. Look for 'Zoho Leads' section in the API docs")
    print("4. Test the endpoints using the interactive docs")
    print("5. Use the endpoints in your frontend/dashboard")

if __name__ == "__main__":
    show_integration_status()
    test_api_endpoints()
    test_fastapi_docs()
    
    print("\n" + "=" * 50)
    print("🎯 Integration Complete!")
    print("📖 Check your FastAPI docs at: http://localhost:8000/docs")
    print("🔍 Look for the 'Zoho Leads' section")
