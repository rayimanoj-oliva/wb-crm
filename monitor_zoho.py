#!/usr/bin/env python3
"""
Zoho Integration Monitor
Real-time monitoring tool for debugging lead creation
"""

import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def monitor_zoho_logs():
    """Monitor Zoho integration logs"""
    
    print("📊 Zoho Integration Monitor")
    print("=" * 50)
    print("This tool helps you monitor and debug the integration")
    print("=" * 50)
    
    # Check if log files exist
    log_patterns = [
        "zoho_lead_service",
        "lead_appointment_flow", 
        "zoho_integration"
    ]
    
    print("🔍 Looking for Zoho-related logs...")
    
    # In a real application, you'd check actual log files
    # For now, we'll show what to look for
    print("\n📝 What to look for in your logs:")
    print("✅ [zoho_lead_service] DEBUG - Starting lead creation")
    print("✅ [zoho_lead_service] DEBUG - Lead created successfully")
    print("✅ [zoho_lead_service] DEBUG - Q5 auto-dial event triggered")
    print("❌ [zoho_lead_service] ERROR - Lead creation failed")
    print("❌ [zoho_lead_service] ERROR - No access token available")

def check_integration_status():
    """Check the current status of the integration"""
    
    print("\n🔍 Checking Integration Status...")
    print("=" * 50)
    
    # Check if files exist
    integration_files = [
        "controllers/components/lead_appointment_flow/zoho_lead_service.py",
        "controllers/components/lead_appointment_flow/callback_confirmation.py",
        "controllers/components/lead_appointment_flow/flow_controller.py"
    ]
    
    print("📁 Checking integration files:")
    
    for file_path in integration_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - MISSING!")
    
    # Check environment
    load_dotenv()
    env_vars = ["ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"]
    
    print("\n🔧 Checking environment variables:")
    
    for var in env_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"❌ {var} - NOT SET")

def create_debug_checklist():
    """Create a debug checklist for troubleshooting"""
    
    print("\n📋 Debug Checklist")
    print("=" * 50)
    
    checklist = [
        "✅ Environment variables set (ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN)",
        "✅ Zoho refresh token is valid and not expired",
        "✅ Zoho CRM API access is enabled",
        "✅ Network connectivity to zohoapis.in",
        "✅ Lead creation permissions in Zoho CRM",
        "✅ Field mapping matches your CRM structure",
        "✅ Triggers (approval, workflow, blueprint) are configured",
        "✅ Auto-dial webhook/API endpoint is accessible",
        "✅ Session state management is working",
        "✅ WhatsApp message flow is triggering correctly"
    ]
    
    for item in checklist:
        print(item)
    
    print("\n🔧 Common Issues & Solutions:")
    print("❌ 'No access token' → Check refresh token and credentials")
    print("❌ 'API Error 401' → Token expired, refresh credentials")
    print("❌ 'API Error 400' → Check field mapping and data format")
    print("❌ 'Connection timeout' → Check network and firewall")
    print("❌ 'Lead creation failed' → Check CRM permissions and field requirements")

def show_test_commands():
    """Show commands to run tests"""
    
    print("\n🧪 Test Commands")
    print("=" * 50)
    
    commands = [
        "python check_zoho_env.py          # Check environment setup",
        "python test_zoho_auth.py          # Test authentication", 
        "python test_lead_creation.py       # Test lead creation",
        "python test_live_flow.py          # Test WhatsApp flow",
        "python test_zoho_integration.py   # Full integration test"
    ]
    
    for cmd in commands:
        print(f"🔹 {cmd}")
    
    print("\n📱 Manual WhatsApp Testing:")
    print("1. Send 'book appointment' to your WhatsApp bot")
    print("2. Complete the flow until Q5 (callback confirmation)")
    print("3. Choose 'Yes' → Should trigger auto-dial")
    print("4. Choose 'No' → Should create follow-up lead")
    print("5. Check Zoho CRM for new leads")

if __name__ == "__main__":
    monitor_zoho_logs()
    check_integration_status()
    create_debug_checklist()
    show_test_commands()
    
    print("\n" + "=" * 50)
    print("🎯 Next Steps:")
    print("1. Run the test commands above")
    print("2. Check your Zoho CRM for created leads")
    print("3. Monitor logs for any errors")
    print("4. Test with real WhatsApp messages")
    print("5. Verify auto-dial triggers (if configured)")
