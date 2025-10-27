#!/usr/bin/env python3
"""
Test Zoho Token Authentication
This will verify your credentials work with Zoho API
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def test_zoho_auth():
    """Test Zoho authentication"""
    
    print("🔐 Testing Zoho Authentication...")
    print("=" * 50)
    
    load_dotenv()
    
    try:
        from utils.zoho_auth import get_valid_access_token
        
        print("📡 Requesting access token...")
        access_token = get_valid_access_token()
        
        if access_token:
            print(f"✅ Access token obtained: {access_token[:20]}...")
            
            # Test API call with the token
            print("🧪 Testing API call...")
            
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json"
            }
            
            # Test with a simple API call (get leads count)
            test_url = "https://www.zohoapis.in/crm/v2.1/Leads"
            
            response = requests.get(test_url, headers=headers, timeout=10)
            
            print(f"📊 API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Authentication successful!")
                print("✅ API access confirmed!")
                
                # Try to get leads data
                try:
                    data = response.json()
                    leads_count = len(data.get('data', []))
                    print(f"📈 Found {leads_count} existing leads in CRM")
                except:
                    print("📋 API response received (data parsing skipped)")
                
            elif response.status_code == 401:
                print("❌ Authentication failed!")
                print("🔧 Check your refresh token and client credentials")
            else:
                print(f"⚠️  Unexpected response: {response.status_code}")
                print(f"📝 Response: {response.text[:200]}...")
                
        else:
            print("❌ Failed to get access token!")
            print("🔧 Check your environment variables")
            
    except Exception as e:
        print(f"❌ Error during authentication test: {str(e)}")
        print("🔧 Check your network connection and credentials")

if __name__ == "__main__":
    test_zoho_auth()
