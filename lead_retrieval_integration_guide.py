"""
Integration Guide for Zoho Lead Retrieval API
How to add the lead retrieval endpoints to your existing FastAPI application
"""

def show_integration_steps():
    """Show steps to integrate the API"""
    
    print("🔌 Zoho Lead Retrieval API Integration Guide")
    print("=" * 60)
    
    print("\n📋 Files Created:")
    print("=" * 30)
    
    files = [
        "controllers/components/lead_appointment_flow/zoho_lead_retrieval.py - Core service",
        "controllers/components/lead_appointment_flow/zoho_lead_api.py - FastAPI endpoints",
        "test_lead_retrieval_api.py - Test script"
    ]
    
    for file in files:
        print(f"   ✅ {file}")
    
    print("\n🔧 Integration Steps:")
    print("=" * 30)
    
    steps = [
        "1. Add the router to your main FastAPI app",
        "2. Test the endpoints",
        "3. Use in your dashboard/frontend",
        "4. Monitor lead creation"
    ]
    
    for step in steps:
        print(f"   🔹 {step}")

def show_fastapi_integration():
    """Show how to integrate with FastAPI"""
    
    print("\n🌐 FastAPI Integration:")
    print("=" * 40)
    
    print("\n📝 Step 1: Add to your main app.py:")
    print("""
from fastapi import FastAPI
from controllers.components.lead_appointment_flow.zoho_lead_api import router as zoho_leads_router

app = FastAPI()

# Add the Zoho leads router
app.include_router(zoho_leads_router)

# Your existing routes...
""")
    
    print("\n📝 Step 2: Test the endpoints:")
    print("""
# Start your FastAPI server
uvicorn app:app --reload

# Test the endpoints
curl "http://localhost:8000/api/zoho-leads/whatsapp?limit=10"
curl "http://localhost:8000/api/zoho-leads/statistics/summary?days=30"
curl "http://localhost:8000/api/zoho-leads/whatsapp/q5-events?days=7"
""")

def show_api_endpoints():
    """Show all available API endpoints"""
    
    print("\n🔗 Available API Endpoints:")
    print("=" * 40)
    
    endpoints = [
        {
            "method": "GET",
            "path": "/api/zoho-leads/whatsapp",
            "description": "Get all WhatsApp source leads",
            "params": "limit, page, sort_order, sort_by, date_from, date_to, lead_status"
        },
        {
            "method": "GET", 
            "path": "/api/zoho-leads/{lead_id}",
            "description": "Get specific lead by ID",
            "params": "lead_id (path parameter)"
        },
        {
            "method": "GET",
            "path": "/api/zoho-leads/statistics/summary",
            "description": "Get lead statistics",
            "params": "days"
        },
        {
            "method": "GET",
            "path": "/api/zoho-leads/whatsapp/q5-events",
            "description": "Get Q5 events (callback requested)",
            "params": "limit, page, days"
        },
        {
            "method": "GET",
            "path": "/api/zoho-leads/whatsapp/termination-events",
            "description": "Get termination events (follow-up leads)",
            "params": "limit, page, days"
        },
        {
            "method": "GET",
            "path": "/api/zoho-leads/whatsapp/pending",
            "description": "Get pending leads",
            "params": "limit, page, days"
        },
        {
            "method": "GET",
            "path": "/api/zoho-leads/health",
            "description": "Health check",
            "params": "none"
        }
    ]
    
    for endpoint in endpoints:
        print(f"\n🔹 {endpoint['method']} {endpoint['path']}")
        print(f"   Description: {endpoint['description']}")
        print(f"   Parameters: {endpoint['params']}")

def show_example_usage():
    """Show example usage of the API"""
    
    print("\n📱 Example Usage:")
    print("=" * 30)
    
    print("\n🔍 Get all WhatsApp leads:")
    print("""
GET /api/zoho-leads/whatsapp?limit=50&page=1&sort_order=desc&sort_by=Created_Time

Response:
{
  "success": true,
  "leads": [
    {
      "id": "123456789",
      "full_name": "John Doe",
      "phone": "919876543210",
      "email": "john@example.com",
      "lead_status": "CALL_INITIATED",
      "appointment_details": {
        "city": "Delhi",
        "clinic": "Main Branch",
        "preferred_date": "2024-01-15",
        "preferred_time": "10:00 AM"
      },
      "created_time": "2024-01-15T10:30:45+05:30"
    }
  ],
  "total_count": 150,
  "page_info": {...},
  "query_info": {...}
}
""")
    
    print("\n📊 Get statistics:")
    print("""
GET /api/zoho-leads/statistics/summary?days=30

Response:
{
  "success": true,
  "statistics": {
    "total_leads": 150,
    "q5_events": 45,
    "termination_events": 60,
    "pending_leads": 45,
    "status_breakdown": {
      "CALL_INITIATED": 45,
      "NO_CALLBACK": 60,
      "PENDING": 45
    },
    "city_breakdown": {
      "Delhi": 80,
      "Mumbai": 40,
      "Bangalore": 30
    }
  }
}
""")
    
    print("\n📞 Get Q5 events only:")
    print("""
GET /api/zoho-leads/whatsapp/q5-events?days=7&limit=20

Response:
{
  "success": true,
  "leads": [
    {
      "id": "123456789",
      "full_name": "John Doe",
      "lead_status": "CALL_INITIATED",
      "appointment_details": {...}
    }
  ],
  "total_count": 15
}
""")

def show_frontend_integration():
    """Show how to use in frontend"""
    
    print("\n🖥️ Frontend Integration:")
    print("=" * 40)
    
    print("\n📝 JavaScript/React Example:")
    print("""
// Get WhatsApp leads
const getWhatsAppLeads = async () => {
  const response = await fetch('/api/zoho-leads/whatsapp?limit=50&lead_status=CALL_INITIATED');
  const data = await response.json();
  return data.leads;
};

// Get statistics
const getLeadStatistics = async (days = 30) => {
  const response = await fetch(`/api/zoho-leads/statistics/summary?days=${days}`);
  const data = await response.json();
  return data.statistics;
};

// Get Q5 events
const getQ5Events = async (days = 7) => {
  const response = await fetch(`/api/zoho-leads/whatsapp/q5-events?days=${days}`);
  const data = await response.json();
  return data.leads;
};
""")
    
    print("\n📝 Python/Requests Example:")
    print("""
import requests

# Get WhatsApp leads
response = requests.get('http://localhost:8000/api/zoho-leads/whatsapp?limit=50')
leads = response.json()['leads']

# Get statistics
response = requests.get('http://localhost:8000/api/zoho-leads/statistics/summary?days=30')
stats = response.json()['statistics']

# Get Q5 events
response = requests.get('http://localhost:8000/api/zoho-leads/whatsapp/q5-events?days=7')
q5_events = response.json()['leads']
""")

def show_monitoring_dashboard():
    """Show how to create a monitoring dashboard"""
    
    print("\n📊 Monitoring Dashboard Ideas:")
    print("=" * 40)
    
    dashboard_features = [
        "📈 Total leads created today/this week/this month",
        "📞 Q5 events (callback requests) count and trend",
        "🔄 Termination events (follow-up leads) count",
        "⏳ Pending leads requiring manual follow-up",
        "🏙️ Lead distribution by city",
        "📅 Daily lead creation trends",
        "📊 Lead status breakdown pie chart",
        "🔍 Search and filter leads by various criteria",
        "📱 Export leads to CSV/Excel",
        "🔔 Real-time notifications for new Q5 events"
    ]
    
    for feature in dashboard_features:
        print(f"   {feature}")
    
    print("\n📝 Dashboard API calls:")
    print("""
// Dashboard data fetching
const dashboardData = {
  // Recent leads
  recentLeads: await fetch('/api/zoho-leads/whatsapp?limit=20&sort_order=desc'),
  
  // Today's statistics
  todayStats: await fetch('/api/zoho-leads/statistics/summary?days=1'),
  
  // This week's Q5 events
  q5Events: await fetch('/api/zoho-leads/whatsapp/q5-events?days=7'),
  
  // This month's termination events
  terminationEvents: await fetch('/api/zoho-leads/whatsapp/termination-events?days=30')
};
""")

if __name__ == "__main__":
    show_integration_steps()
    show_fastapi_integration()
    show_api_endpoints()
    show_example_usage()
    show_frontend_integration()
    show_monitoring_dashboard()
    
    print("\n" + "=" * 60)
    print("🎯 Summary:")
    print("✅ Complete lead retrieval API created")
    print("✅ FastAPI endpoints ready to use")
    print("✅ Statistics and filtering capabilities")
    print("✅ Q5 and termination event tracking")
    print("✅ Easy frontend integration")
    print("\n📱 Next Steps:")
    print("1. Add router to your FastAPI app")
    print("2. Test the endpoints")
    print("3. Build your monitoring dashboard")
    print("4. Track lead conversion rates")
