#!/usr/bin/env python3
"""
Test Script for Recent Leads API
Demonstrates the new recent leads endpoints
"""

import requests
import json
from datetime import datetime

def test_recent_leads_api():
    """Test the recent leads API endpoints"""
    
    print("📥 Testing Recent Leads API")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test endpoints
    endpoints = [
        {
            "name": "Latest Leads",
            "url": f"{base_url}/api/zoho-leads/whatsapp/latest?limit=5",
            "description": "Get the 5 most recent leads"
        },
        {
            "name": "Today's Leads",
            "url": f"{base_url}/api/zoho-leads/whatsapp/today?limit=10",
            "description": "Get today's leads"
        },
        {
            "name": "Recent Leads (24 hours)",
            "url": f"{base_url}/api/zoho-leads/whatsapp/recent?limit=10&hours=24",
            "description": "Get leads from last 24 hours"
        },
        {
            "name": "This Week's Leads",
            "url": f"{base_url}/api/zoho-leads/whatsapp/this-week?limit=20",
            "description": "Get this week's leads"
        },
        {
            "name": "Recent Leads (6 hours)",
            "url": f"{base_url}/api/zoho-leads/whatsapp/recent?limit=5&hours=6",
            "description": "Get leads from last 6 hours"
        }
    ]
    
    print("🔍 Testing Recent Leads Endpoints...")
    print("=" * 50)
    
    for endpoint in endpoints:
        print(f"\n🔹 Testing {endpoint['name']}...")
        print(f"   Description: {endpoint['description']}")
        print(f"   URL: {endpoint['url']}")
        
        try:
            response = requests.get(endpoint['url'], timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                leads = data.get('leads', [])
                
                print(f"   ✅ SUCCESS! Found {len(leads)} leads")
                
                if leads:
                    # Show first lead details
                    first_lead = leads[0]
                    print(f"   📋 Sample Lead:")
                    print(f"      ID: {first_lead.get('id')}")
                    print(f"      Name: {first_lead.get('full_name')}")
                    print(f"      Phone: {first_lead.get('phone')}")
                    print(f"      Status: {first_lead.get('lead_status')}")
                    print(f"      Created: {first_lead.get('created_time')}")
                    print(f"      City: {first_lead.get('appointment_details', {}).get('city')}")
                
                # Show query info
                query_info = data.get('query_info', {})
                if query_info:
                    print(f"   📊 Query Info:")
                    for key, value in query_info.items():
                        if key not in ['query']:  # Skip long query string
                            print(f"      {key}: {value}")
            else:
                print(f"   ❌ FAILED! Status: {response.status_code}")
                print(f"   📄 Response: {response.text[:200]}...")
                
        except requests.exceptions.ConnectionError:
            print(f"   ❌ CONNECTION ERROR! Is your FastAPI server running?")
        except Exception as e:
            print(f"   ❌ EXCEPTION! {str(e)}")

def show_api_examples():
    """Show example API calls"""
    
    print("\n📝 Recent Leads API Examples")
    print("=" * 50)
    
    examples = [
        {
            "title": "Get Latest 10 Leads",
            "curl": 'curl "http://localhost:8000/api/zoho-leads/whatsapp/latest?limit=10"',
            "description": "Most recent leads first"
        },
        {
            "title": "Get Today's Leads",
            "curl": 'curl "http://localhost:8000/api/zoho-leads/whatsapp/today?limit=20"',
            "description": "All leads created today"
        },
        {
            "title": "Get Leads from Last 6 Hours",
            "curl": 'curl "http://localhost:8000/api/zoho-leads/whatsapp/recent?limit=15&hours=6"',
            "description": "Recent activity"
        },
        {
            "title": "Get This Week's Leads",
            "curl": 'curl "http://localhost:8000/api/zoho-leads/whatsapp/this-week?limit=50"',
            "description": "Weekly summary"
        },
        {
            "title": "Get Leads from Last 2 Hours",
            "curl": 'curl "http://localhost:8000/api/zoho-leads/whatsapp/recent?limit=5&hours=2"',
            "description": "Very recent activity"
        }
    ]
    
    for example in examples:
        print(f"\n🔹 {example['title']}")
        print(f"   Description: {example['description']}")
        print(f"   Command: {example['curl']}")

def show_javascript_examples():
    """Show JavaScript examples for frontend integration"""
    
    print("\n🖥️ JavaScript/Frontend Examples")
    print("=" * 50)
    
    js_examples = [
        {
            "title": "Get Latest Leads",
            "code": """
// Get latest 10 leads
const getLatestLeads = async () => {
  const response = await fetch('/api/zoho-leads/whatsapp/latest?limit=10');
  const data = await response.json();
  return data.leads;
};
"""
        },
        {
            "title": "Get Today's Leads",
            "code": """
// Get today's leads
const getTodaysLeads = async () => {
  const response = await fetch('/api/zoho-leads/whatsapp/today?limit=20');
  const data = await response.json();
  return data.leads;
};
"""
        },
        {
            "title": "Get Recent Leads (Custom Hours)",
            "code": """
// Get leads from last 6 hours
const getRecentLeads = async (hours = 6) => {
  const response = await fetch(`/api/zoho-leads/whatsapp/recent?limit=15&hours=${hours}`);
  const data = await response.json();
  return data.leads;
};
"""
        },
        {
            "title": "Dashboard Data Fetching",
            "code": """
// Dashboard with multiple recent data sources
const dashboardData = {
  latestLeads: await fetch('/api/zoho-leads/whatsapp/latest?limit=5'),
  todaysLeads: await fetch('/api/zoho-leads/whatsapp/today?limit=20'),
  recentActivity: await fetch('/api/zoho-leads/whatsapp/recent?limit=10&hours=6'),
  weeklySummary: await fetch('/api/zoho-leads/whatsapp/this-week?limit=50')
};
"""
        }
    ]
    
    for example in js_examples:
        print(f"\n🔹 {example['title']}")
        print(example['code'])

def show_use_cases():
    """Show practical use cases for recent leads API"""
    
    print("\n🎯 Practical Use Cases")
    print("=" * 50)
    
    use_cases = [
        {
            "title": "Real-time Dashboard",
            "description": "Show latest leads on your admin dashboard",
            "endpoint": "/api/zoho-leads/whatsapp/latest?limit=10",
            "refresh": "Every 30 seconds"
        },
        {
            "title": "Today's Activity",
            "description": "Monitor today's lead generation",
            "endpoint": "/api/zoho-leads/whatsapp/today?limit=50",
            "refresh": "Every hour"
        },
        {
            "title": "Recent Activity Alert",
            "description": "Get notified of new leads in last 2 hours",
            "endpoint": "/api/zoho-leads/whatsapp/recent?limit=5&hours=2",
            "refresh": "Every 5 minutes"
        },
        {
            "title": "Weekly Report",
            "description": "Generate weekly lead reports",
            "endpoint": "/api/zoho-leads/whatsapp/this-week?limit=200",
            "refresh": "Daily"
        },
        {
            "title": "Live Monitoring",
            "description": "Monitor leads from last 6 hours",
            "endpoint": "/api/zoho-leads/whatsapp/recent?limit=20&hours=6",
            "refresh": "Every 2 minutes"
        }
    ]
    
    for use_case in use_cases:
        print(f"\n🔹 {use_case['title']}")
        print(f"   Description: {use_case['description']}")
        print(f"   Endpoint: {use_case['endpoint']}")
        print(f"   Refresh: {use_case['refresh']}")

if __name__ == "__main__":
    test_recent_leads_api()
    show_api_examples()
    show_javascript_examples()
    show_use_cases()
    
    print("\n" + "=" * 50)
    print("🎯 Recent Leads API Summary:")
    print("✅ /api/zoho-leads/whatsapp/latest - Most recent leads")
    print("✅ /api/zoho-leads/whatsapp/today - Today's leads")
    print("✅ /api/zoho-leads/whatsapp/recent - Custom hours back")
    print("✅ /api/zoho-leads/whatsapp/this-week - This week's leads")
    print("\n📱 Perfect for:")
    print("🔹 Real-time dashboards")
    print("🔹 Activity monitoring")
    print("🔹 Recent lead alerts")
    print("🔹 Live lead tracking")
    print("\n🌐 Test at: http://localhost:8000/docs")
