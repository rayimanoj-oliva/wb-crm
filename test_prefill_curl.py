#!/usr/bin/env python3
"""
Test prefill message through website using curl
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def test_prefill_message():
    """Test prefill message with referrer tracking"""
    print("🧪 Testing Prefill Message with Referrer Tracking")
    print("=" * 55)
    
    # Test with different centers
    test_cases = [
        {
            "wa_id": "918309867000",
            "center": "Banjara Hills",
            "utm_campaign": "banjara_hills",
            "location": "Hyderabad",
            "message": "Hi, I want to book an appointment. I came from banjara.olivaclinics.com"
        },
        {
            "wa_id": "918309867001",
            "center": "Jubilee Hills", 
            "utm_campaign": "jubilee_hills",
            "location": "Hyderabad",
            "message": "Hello, I need to book an appointment at Jubilee Hills center"
        },
        {
            "wa_id": "918309867002",
            "center": "Bandra",
            "utm_campaign": "mumbai_bandra",
            "location": "Mumbai",
            "message": "Hi, I want to book an appointment at Bandra center"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing {test_case['center']} center...")
        
        # Simulate webhook payload with referrer information
        webhook_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{
                            "wa_id": test_case["wa_id"],
                            "profile": {
                                "name": f"Test User {test_case['center']}"
                            }
                        }],
                        "messages": [{
                            "from": test_case["wa_id"],
                            "id": f"prefill_test_{i}",
                            "timestamp": str(int(datetime.now().timestamp())),
                            "type": "text",
                            "text": {
                                "body": test_case["message"]
                            }
                        }],
                        "metadata": {
                            "display_phone_number": "917729992376"
                        }
                    }
                }]
            }]
        }
        
        print(f"   📱 WA ID: {test_case['wa_id']}")
        print(f"   💬 Message: {test_case['message']}")
        
        try:
            # Send webhook request
            response = requests.post(
                f"{BASE_URL}/ws/webhook",
                json=webhook_payload,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"   📡 Webhook Status: {response.status_code}")
            
            if response.status_code == 200:
                print("   ✅ Webhook processed successfully!")
                
                # Wait a moment for processing
                import time
                time.sleep(2)
                
                # Check if referrer tracking was created
                print("   🔍 Checking referrer tracking...")
                referrer_response = requests.get(
                    f"{BASE_URL}/referrer/{test_case['wa_id']}",
                    headers={"accept": "application/json"}
                )
                
                if referrer_response.status_code == 200:
                    data = referrer_response.json()
                    print("   ✅ Referrer tracking found!")
                    print(f"      🏥 Center: {data['center_name']}")
                    print(f"      📍 Location: {data['location']}")
                    print(f"      🏷️  UTM Campaign: {data['utm_campaign']}")
                else:
                    print("   ❌ No referrer tracking found")
            else:
                print(f"   ❌ Webhook failed: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

def test_utm_parameters():
    """Test with UTM parameters in message"""
    print("\n🔗 Testing UTM Parameters in Message")
    print("=" * 40)
    
    wa_id = "918309867003"
    
    # Message with UTM parameters
    utm_message = "utm_source=olivaclinics&utm_medium=website&utm_campaign=gachibowli&utm_content=hyderabad"
    
    webhook_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{
                        "wa_id": wa_id,
                        "profile": {
                            "name": "UTM Test User"
                        }
                    }],
                    "messages": [{
                        "from": wa_id,
                        "id": "utm_test_123",
                        "timestamp": str(int(datetime.now().timestamp())),
                        "type": "text",
                        "text": {
                            "body": utm_message
                        }
                    }],
                    "metadata": {
                        "display_phone_number": "917729992376"
                    }
                }
            }]
        }]
    }
    
    print(f"📱 WA ID: {wa_id}")
    print(f"💬 UTM Message: {utm_message}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/ws/webhook",
            json=webhook_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"📡 Webhook Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Webhook processed successfully!")
            
            # Check referrer tracking
            referrer_response = requests.get(
                f"{BASE_URL}/referrer/{wa_id}",
                headers={"accept": "application/json"}
            )
            
            if referrer_response.status_code == 200:
                data = referrer_response.json()
                print("✅ Referrer tracking found!")
                print(f"   🏥 Center: {data['center_name']}")
                print(f"   📍 Location: {data['location']}")
                print(f"   🏷️  UTM Campaign: {data['utm_campaign']}")
            else:
                print("❌ No referrer tracking found")
        else:
            print(f"❌ Webhook failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def show_curl_commands():
    """Show curl commands for testing"""
    print("\n📋 Curl Commands for Testing")
    print("=" * 35)
    
    print("🔗 Test webhook with referrer tracking:")
    print("""
curl -X POST "http://127.0.0.1:8000/ws/webhook" \\
  -H "Content-Type: application/json" \\
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "contacts": [{
            "wa_id": "918309867004",
            "profile": {"name": "Curl Test User"}
          }],
          "messages": [{
            "from": "918309867004",
            "id": "curl_test_123",
            "timestamp": "1758972000",
            "type": "text",
            "text": {"body": "Hi, I want to book an appointment at Banjara Hills"}
          }],
          "metadata": {"display_phone_number": "917729992376"}
        }
      }]
    }]
  }'
    """)
    
    print("🔍 Check referrer tracking:")
    print("""
curl -X GET "http://127.0.0.1:8000/referrer/918309867004" \\
  -H "accept: application/json"
    """)
    
    print("📊 Get all referrer records:")
    print("""
curl -X GET "http://127.0.0.1:8000/referrer/" \\
  -H "accept: application/json"
    """)

if __name__ == "__main__":
    print("🚀 Prefill Message Testing Suite")
    print("=" * 50)
    
    test_prefill_message()
    test_utm_parameters()
    show_curl_commands()
    
    print("\n🎉 Testing completed!")
    print("\n📋 Summary:")
    print("- Tested prefill messages with referrer tracking")
    print("- Tested UTM parameter detection")
    print("- Provided curl commands for manual testing")
