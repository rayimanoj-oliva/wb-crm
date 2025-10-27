#!/usr/bin/env python3
"""
Quick Environment Check for Zoho Integration
Run this first to verify your setup
"""

import os
import sys
from dotenv import load_dotenv

def check_environment():
    """Check if all required environment variables are set"""
    
    print("🔍 Checking Zoho Integration Environment...")
    print("=" * 50)
    
    # Load environment variables
    load_dotenv()
    
    required_vars = {
        "ZOHO_CLIENT_ID": os.getenv("ZOHO_CLIENT_ID"),
        "ZOHO_CLIENT_SECRET": os.getenv("ZOHO_CLIENT_SECRET"), 
        "ZOHO_REFRESH_TOKEN": os.getenv("ZOHO_REFRESH_TOKEN")
    }
    
    all_good = True
    
    for var_name, var_value in required_vars.items():
        if var_value:
            print(f"✅ {var_name}: {'*' * 10}{var_value[-4:] if len(var_value) > 4 else '****'}")
        else:
            print(f"❌ {var_name}: NOT SET")
            all_good = False
    
    print("\n" + "=" * 50)
    
    if all_good:
        print("🎉 All environment variables are set!")
        print("✅ Ready to test Zoho integration")
    else:
        print("⚠️  Missing environment variables!")
        print("📝 Please set the missing variables in your .env file")
        print("\nExample .env file:")
        print("ZOHO_CLIENT_ID=your_client_id_here")
        print("ZOHO_CLIENT_SECRET=your_client_secret_here")
        print("ZOHO_REFRESH_TOKEN=your_refresh_token_here")
    
    return all_good

if __name__ == "__main__":
    check_environment()
