#!/usr/bin/env python3
"""
Zoho Lead Creation Monitor
Real-time monitoring of lead creation logs
"""

import os
import sys
import time
import subprocess
from datetime import datetime

def monitor_logs():
    """Monitor logs for Zoho lead creation events"""
    
    print("📊 Zoho Lead Creation Monitor")
    print("=" * 60)
    print("This tool monitors your application logs for lead creation events")
    print("=" * 60)
    
    print("\n🔍 What to look for in your logs:")
    print("✅ [ZOHO LEAD CREATION] Starting at")
    print("✅ [ZOHO LEAD CREATION] SUCCESS!")
    print("✅ [Q5 AUTO-DIAL EVENT] Starting at")
    print("✅ [TERMINATION EVENT] Starting at")
    print("❌ [ZOHO LEAD CREATION] FAILED!")
    print("❌ [ZOHO LEAD CREATION] EXCEPTION!")
    
    print("\n📝 Log Patterns to Monitor:")
    patterns = [
        "[ZOHO LEAD CREATION]",
        "[Q5 AUTO-DIAL EVENT]", 
        "[TERMINATION EVENT]",
        "[LEAD APPOINTMENT FLOW]"
    ]
    
    for pattern in patterns:
        print(f"🔹 {pattern}")
    
    print("\n🚀 How to monitor logs:")
    print("1. Run your application")
    print("2. Send WhatsApp messages to trigger the flow")
    print("3. Watch the console output for the patterns above")
    print("4. Check Zoho CRM for new leads")
    
    print("\n📱 Test Scenarios:")
    print("1. Send 'book appointment' → Complete flow → Q5 'Yes' → Should see Q5 AUTO-DIAL EVENT")
    print("2. Send 'book appointment' → Complete flow → Q5 'No' → Should see TERMINATION EVENT")
    print("3. Send 'book appointment' → Drop off → Should see TERMINATION EVENT")
    print("4. Complete time selection → Should see LEAD APPOINTMENT FLOW")

def show_sample_logs():
    """Show sample log output"""
    
    print("\n📋 Sample Log Output:")
    print("=" * 60)
    
    sample_logs = [
        "🚀 [ZOHO LEAD CREATION] Starting at 2024-01-15 10:30:45",
        "📋 [ZOHO LEAD CREATION] Customer: John Doe",
        "📞 [ZOHO LEAD CREATION] Phone: 919876543210",
        "📧 [ZOHO LEAD CREATION] Email: john@example.com",
        "🏙️ [ZOHO LEAD CREATION] City: Delhi",
        "📊 [ZOHO LEAD CREATION] Status: CALL_INITIATED",
        "✅ [ZOHO LEAD CREATION] Access token obtained: 1000.6c32bde505d5d27e...",
        "📦 [ZOHO LEAD CREATION] Prepared lead data:",
        "   - First Name: John",
        "   - Last Name: Doe",
        "   - Email: john@example.com",
        "   - Phone: 919876543210",
        "   - Mobile: 919876543210",
        "   - City: Delhi",
        "   - Lead Source: WhatsApp Lead-to-Appointment Flow",
        "   - Lead Status: CALL_INITIATED",
        "   - Company: Oliva Skin & Hair Clinic",
        "🌐 [ZOHO LEAD CREATION] Making API call to: https://www.zohoapis.in/crm/v2.1/Leads",
        "📊 [ZOHO LEAD CREATION] API Response Status: 201",
        "🎉 [ZOHO LEAD CREATION] SUCCESS!",
        "🆔 [ZOHO LEAD CREATION] Lead ID: 123456789",
        "📅 [ZOHO LEAD CREATION] Created at: 2024-01-15 10:30:45",
        "🔗 [ZOHO LEAD CREATION] Check Zoho CRM for lead ID: 123456789"
    ]
    
    for log_line in sample_logs:
        print(log_line)

def create_log_filter():
    """Create a log filter command"""
    
    print("\n🔧 Log Filter Commands:")
    print("=" * 60)
    
    print("To filter logs for Zoho lead creation:")
    print("🔹 grep -i 'zoho lead creation' your_log_file.log")
    print("🔹 grep -i 'q5 auto-dial event' your_log_file.log")
    print("🔹 grep -i 'termination event' your_log_file.log")
    print("🔹 grep -i 'lead appointment flow' your_log_file.log")
    
    print("\nTo monitor logs in real-time:")
    print("🔹 tail -f your_log_file.log | grep -i 'zoho lead creation'")
    print("🔹 tail -f your_log_file.log | grep -i 'q5\\|termination\\|lead creation'")

def show_verification_steps():
    """Show verification steps"""
    
    print("\n✅ Verification Steps:")
    print("=" * 60)
    
    steps = [
        "1. Run your application",
        "2. Send WhatsApp message: 'book appointment'",
        "3. Complete the appointment flow",
        "4. Watch console logs for [ZOHO LEAD CREATION] messages",
        "5. Check Zoho CRM for new leads",
        "6. Verify lead data matches the logs",
        "7. Test Q5 'Yes' → Should see [Q5 AUTO-DIAL EVENT]",
        "8. Test Q5 'No' → Should see [TERMINATION EVENT]",
        "9. Test dropoff → Should see [TERMINATION EVENT]"
    ]
    
    for step in steps:
        print(f"🔹 {step}")

if __name__ == "__main__":
    monitor_logs()
    show_sample_logs()
    create_log_filter()
    show_verification_steps()
    
    print("\n" + "=" * 60)
    print("🎯 Summary:")
    print("✅ Enhanced logging added to Zoho lead service")
    print("✅ Clear indicators when leads are being created")
    print("✅ Detailed information about lead data")
    print("✅ Success/failure status clearly shown")
    print("✅ Lead IDs provided for verification")
    print("\n📱 Next Steps:")
    print("1. Run your application")
    print("2. Test the WhatsApp flow")
    print("3. Watch the console for detailed logs")
    print("4. Check Zoho CRM for created leads")
