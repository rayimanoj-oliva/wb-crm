#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WhatsApp Configuration Checker
Verifies that WABA ID and Phone ID are correctly configured
"""

import os
import sys
from dotenv import load_dotenv

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def check_whatsapp_config():
    """Check WhatsApp configuration"""
    
    print("Checking WhatsApp Configuration...")
    print("=" * 60)
    
    # Load environment variables
    load_dotenv()
    
    waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    
    print(f"\nCurrent Configuration:")
    print(f"   WHATSAPP_BUSINESS_ACCOUNT_ID: {waba_id or 'NOT SET (using default: 286831244524604)'}")
    print(f"   WHATSAPP_PHONE_ID: {phone_id}")
    print()
    
    # Check for common mistakes
    issues = []
    warnings = []
    
    if not waba_id:
        warnings.append("WARNING: WHATSAPP_BUSINESS_ACCOUNT_ID is not set. Using default: 286831244524604")
    elif waba_id == phone_id:
        issues.append(f"CRITICAL: WHATSAPP_BUSINESS_ACCOUNT_ID ({waba_id}) is the same as Phone ID!")
        issues.append("   WABA ID and Phone ID must be different values.")
        issues.append("   This will cause template creation to fail.")
    elif waba_id == "367633743092037":
        issues.append(f"CRITICAL: WHATSAPP_BUSINESS_ACCOUNT_ID is set to Phone ID ({waba_id})!")
        issues.append("   This is incorrect. WABA ID should be different (e.g., 286831244524604).")
        issues.append("   Template creation will fail with 'Object does not exist' error.")
    
    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"   {issue}")
        print()
        print("SOLUTION:")
        print("   1. Find your actual WABA ID:")
        print("      - Meta Business Suite: https://business.facebook.com")
        print("      - Graph API Explorer: Query 'me?fields=whatsapp_business_accounts'")
        print()
        print("   2. Set the environment variable:")
        print("      Windows PowerShell: $env:WHATSAPP_BUSINESS_ACCOUNT_ID='286831244524604'")
        print("      Windows CMD: set WHATSAPP_BUSINESS_ACCOUNT_ID=286831244524604")
        print("      Linux/Mac: export WHATSAPP_BUSINESS_ACCOUNT_ID='286831244524604'")
        print()
        print("   3. Or add to .env file:")
        print("      WHATSAPP_BUSINESS_ACCOUNT_ID=286831244524604")
        print("      WHATSAPP_PHONE_ID=367633743092037")
        print()
        return False
    
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"   {warning}")
        print()
    
    print("Configuration looks good!")
    print()
    print("Summary:")
    print(f"   WABA ID (for templates): {waba_id or '286831244524604 (default)'}")
    print(f"   Phone ID (for messages): {phone_id}")
    print()
    
    if waba_id and waba_id != phone_id:
        print("WABA ID and Phone ID are different - correct!")
    
    return True

if __name__ == "__main__":
    success = check_whatsapp_config()
    exit(0 if success else 1)

