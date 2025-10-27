#!/usr/bin/env python3
"""
API Requirements Guide for Zoho Lead Creation Integration
This document outlines all the APIs needed for the integration to work
"""

def show_api_requirements():
    """Show all API requirements for the Zoho integration"""
    
    print("🔌 API Requirements for Zoho Lead Creation Integration")
    print("=" * 70)
    
    print("\n📋 REQUIRED APIs:")
    print("=" * 50)
    
    # Required APIs
    required_apis = [
        {
            "name": "Zoho OAuth Token API",
            "url": "https://accounts.zoho.in/oauth/v2/token",
            "method": "POST",
            "purpose": "Get access tokens for Zoho CRM API calls",
            "status": "✅ IMPLEMENTED",
            "details": "Used by utils/zoho_auth.py to refresh access tokens"
        },
        {
            "name": "Zoho CRM Leads API",
            "url": "https://www.zohoapis.in/crm/v2.1/Leads",
            "method": "POST",
            "purpose": "Create leads in Zoho CRM",
            "status": "✅ IMPLEMENTED",
            "details": "Main API for creating leads with your curl structure"
        }
    ]
    
    for api in required_apis:
        print(f"\n🔹 {api['name']}")
        print(f"   URL: {api['url']}")
        print(f"   Method: {api['method']}")
        print(f"   Purpose: {api['purpose']}")
        print(f"   Status: {api['status']}")
        print(f"   Details: {api['details']}")
    
    print("\n📋 OPTIONAL APIs (For Enhanced Features):")
    print("=" * 50)
    
    # Optional APIs
    optional_apis = [
        {
            "name": "Zoho Auto-Dial API",
            "url": "YOUR_AUTO_DIAL_ENDPOINT",
            "method": "POST",
            "purpose": "Trigger automatic phone calls for Q5 events",
            "status": "⚠️ NOT IMPLEMENTED",
            "details": "You need to configure this endpoint for auto-dial functionality",
            "implementation": "Update trigger_q5_auto_dial_event() function"
        },
        {
            "name": "Zoho CRM Custom Functions",
            "url": "https://www.zohoapis.in/crm/v2/functions/YOUR_FUNCTION/actions/execute",
            "method": "POST",
            "purpose": "Execute custom Zoho CRM functions for workflows",
            "status": "⚠️ NOT IMPLEMENTED",
            "details": "Optional for custom business logic",
            "implementation": "Add custom function calls as needed"
        },
        {
            "name": "Zoho CRM Webhooks",
            "url": "YOUR_WEBHOOK_ENDPOINT",
            "method": "POST",
            "purpose": "Receive notifications when leads are created/updated",
            "status": "⚠️ NOT IMPLEMENTED",
            "details": "Optional for real-time notifications",
            "implementation": "Configure webhook endpoints in Zoho CRM"
        }
    ]
    
    for api in optional_apis:
        print(f"\n🔹 {api['name']}")
        print(f"   URL: {api['url']}")
        print(f"   Method: {api['method']}")
        print(f"   Purpose: {api['purpose']}")
        print(f"   Status: {api['status']}")
        print(f"   Details: {api['details']}")
        if 'implementation' in api:
            print(f"   Implementation: {api['implementation']}")

def show_current_implementation():
    """Show what's currently implemented"""
    
    print("\n✅ CURRENTLY IMPLEMENTED:")
    print("=" * 50)
    
    implemented_features = [
        "✅ Zoho OAuth token refresh (utils/zoho_auth.py)",
        "✅ Lead creation API (zoho_lead_service.py)",
        "✅ Q5 auto-dial event trigger (logs the event)",
        "✅ Termination event handling (creates follow-up leads)",
        "✅ Comprehensive logging and error handling",
        "✅ Field mapping matching your curl structure",
        "✅ Session state integration",
        "✅ WhatsApp flow integration"
    ]
    
    for feature in implemented_features:
        print(f"   {feature}")
    
    print("\n⚠️ NEEDS CONFIGURATION:")
    print("=" * 50)
    
    needs_config = [
        "⚠️ Environment variables (ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN)",
        "⚠️ Auto-dial API endpoint (for actual phone calls)",
        "⚠️ Zoho CRM permissions (lead creation access)",
        "⚠️ Field validation (ensure your CRM fields match the API calls)"
    ]
    
    for item in needs_config:
        print(f"   {item}")

def show_api_endpoints():
    """Show detailed API endpoint information"""
    
    print("\n🌐 DETAILED API ENDPOINTS:")
    print("=" * 50)
    
    print("\n1️⃣ Zoho OAuth Token API:")
    print("   URL: https://accounts.zoho.in/oauth/v2/token")
    print("   Method: POST")
    print("   Headers: Content-Type: application/x-www-form-urlencoded")
    print("   Body:")
    print("     - refresh_token: YOUR_REFRESH_TOKEN")
    print("     - client_id: YOUR_CLIENT_ID")
    print("     - client_secret: YOUR_CLIENT_SECRET")
    print("     - grant_type: refresh_token")
    print("   Response: { 'access_token': '...', 'expires_in': 3600 }")
    
    print("\n2️⃣ Zoho CRM Leads API:")
    print("   URL: https://www.zohoapis.in/crm/v2.1/Leads")
    print("   Method: POST")
    print("   Headers:")
    print("     - Authorization: Zoho-oauthtoken {access_token}")
    print("     - Content-Type: application/json")
    print("     - Cookie: _zcsr_tmp=...; crmcsr=...; zalb_...=...")
    print("   Body: Your curl structure")
    print("   Response: { 'data': [{ 'details': { 'id': '123456789' } }] }")

def show_environment_setup():
    """Show environment setup requirements"""
    
    print("\n🔧 ENVIRONMENT SETUP:")
    print("=" * 50)
    
    print("\n📝 Required Environment Variables:")
    env_vars = [
        ("ZOHO_CLIENT_ID", "Your Zoho OAuth client ID"),
        ("ZOHO_CLIENT_SECRET", "Your Zoho OAuth client secret"),
        ("ZOHO_REFRESH_TOKEN", "Your Zoho OAuth refresh token")
    ]
    
    for var, description in env_vars:
        print(f"   {var}: {description}")
    
    print("\n📁 .env File Example:")
    print("   ZOHO_CLIENT_ID=1000.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("   ZOHO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("   ZOHO_REFRESH_TOKEN=1000.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

def show_testing_apis():
    """Show how to test the APIs"""
    
    print("\n🧪 TESTING THE APIs:")
    print("=" * 50)
    
    print("\n1️⃣ Test OAuth Token:")
    print("   python test_zoho_auth.py")
    print("   - Verifies your credentials work")
    print("   - Tests token refresh")
    print("   - Checks API connectivity")
    
    print("\n2️⃣ Test Lead Creation:")
    print("   python test_lead_creation.py")
    print("   - Creates a test lead")
    print("   - Verifies field mapping")
    print("   - Checks API response")
    
    print("\n3️⃣ Test Full Flow:")
    print("   python test_live_flow.py")
    print("   - Simulates WhatsApp interactions")
    print("   - Tests Q5 and termination events")
    print("   - Verifies complete integration")

def show_troubleshooting():
    """Show common API issues and solutions"""
    
    print("\n🔧 TROUBLESHOOTING:")
    print("=" * 50)
    
    issues = [
        {
            "issue": "401 Unauthorized",
            "cause": "Invalid or expired access token",
            "solution": "Check refresh token and client credentials"
        },
        {
            "issue": "400 Bad Request",
            "cause": "Invalid field mapping or data format",
            "solution": "Verify field names match your Zoho CRM structure"
        },
        {
            "issue": "403 Forbidden",
            "cause": "Insufficient permissions",
            "solution": "Check Zoho CRM user permissions for lead creation"
        },
        {
            "issue": "Connection timeout",
            "cause": "Network or firewall issues",
            "solution": "Check network connectivity to zohoapis.in"
        }
    ]
    
    for item in issues:
        print(f"\n❌ {item['issue']}")
        print(f"   Cause: {item['cause']}")
        print(f"   Solution: {item['solution']}")

if __name__ == "__main__":
    show_api_requirements()
    show_current_implementation()
    show_api_endpoints()
    show_environment_setup()
    show_testing_apis()
    show_troubleshooting()
    
    print("\n" + "=" * 70)
    print("🎯 SUMMARY:")
    print("✅ Core APIs are implemented and ready to use")
    print("⚠️ You need to configure environment variables")
    print("⚠️ Auto-dial API endpoint needs to be configured")
    print("📱 Test with the provided test scripts")
    print("🔗 Check Zoho CRM for created leads")
