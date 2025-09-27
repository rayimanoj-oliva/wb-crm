#!/usr/bin/env python3
"""
Test referrer header detection
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def test_with_referrer_header():
    """Test webhook with referrer header"""
    print("🔍 Testing Referrer Header Detection")
    print("=" * 40)
    
    wa_id = "918309867200"
    
    # Webhook payload
    webhook_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{
                        "wa_id": wa_id,
                        "profile": {"name": "Referrer Header Test User"}
                    }],
                    "messages": [{
                        "from": wa_id,
                        "id": "referrer_header_test",
                        "timestamp": str(int(datetime.now().timestamp())),
                        "type": "text",
                        "text": {"body": "Hi, I want to book an appointment"}
                    }],
                    "metadata": {"display_phone_number": "917729992376"}
                }
            }]
        }]
    }
    
    # Headers with referrer information
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://banjara.olivaclinics.com/contact"
    }
    
    print(f"📱 WA ID: {wa_id}")
    print(f"🌐 Referrer URL: {headers['Referer']}")
    print(f"💬 Message: Hi, I want to book an appointment")
    
    try:
        # Send webhook request with referrer header
        response = requests.post(
            f"{BASE_URL}/ws/webhook",
            json=webhook_payload,
            headers=headers
        )
        
        print(f"📡 Webhook Status: {response.status_code}")
        print(f"📡 Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook processed successfully!")
            
            # Wait for processing
            import time
            time.sleep(3)
            
            # Check referrer tracking
            print("\n🔍 Checking referrer tracking...")
            referrer_response = requests.get(
                f"{BASE_URL}/referrer/{wa_id}",
                headers={"accept": "application/json"}
            )
            
            print(f"📊 Referrer API Status: {referrer_response.status_code}")
            
            if referrer_response.status_code == 200:
                data = referrer_response.json()
                print("✅ Referrer tracking found!")
                print(f"   🏥 Center: {data['center_name']}")
                print(f"   📍 Location: {data['location']}")
                print(f"   🏷️  UTM Campaign: {data['utm_campaign']}")
                print(f"   🌐 Referrer URL: {data['referrer_url']}")
                
                # Check if website detection worked
                if "Banjara Hills" in data['center_name'] and "Hyderabad" in data['location']:
                    print("✅ Website detection working correctly!")
                else:
                    print("❌ Website detection not working properly")
            else:
                print("❌ No referrer tracking found")
                print(f"Response: {referrer_response.text}")
        else:
            print(f"❌ Webhook failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def test_curl_with_referrer():
    """Test curl command with referrer header"""
    print("\n📋 Curl Command with Referrer Header")
    print("=" * 40)
    
    curl_command = '''
curl -X POST "http://127.0.0.1:8000/ws/webhook" \\
  -H "Content-Type: application/json" \\
  -H "Referer: https://banjara.olivaclinics.com/contact" \\
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "contacts": [{
            "wa_id": "918309867201",
            "profile": {"name": "Curl Referrer Test"}
          }],
          "messages": [{
            "from": "918309867201",
            "id": "curl_referrer_test",
            "timestamp": "1758972000",
            "type": "text",
            "text": {"body": "Hi, I want to book an appointment"}
          }],
          "metadata": {"display_phone_number": "917729992376"}
        }
      }]
    }]
  }'
    '''
    
    print("🔗 Use this curl command to test:")
    print(curl_command)
    
    print("\n🔍 Then check the result with:")
    print('curl -X GET "http://127.0.0.1:8000/referrer/918309867201" -H "accept: application/json"')

if __name__ == "__main__":
    print("🚀 Referrer Header Detection Test")
    print("=" * 45)
    
    test_with_referrer_header()
    test_curl_with_referrer()
    
    print("\n🎉 Testing completed!")
    print("\n📋 Expected Results:")
    print("- Center: Oliva Clinics Banjara Hills")
    print("- Location: Hyderabad")
    print("- Referrer URL: https://banjara.olivaclinics.com/contact")
