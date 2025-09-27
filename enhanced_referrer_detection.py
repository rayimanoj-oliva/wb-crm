#!/usr/bin/env python3
"""
Enhanced referrer detection for website integration
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def test_enhanced_referrer_detection():
    """Test enhanced referrer detection with multiple sources"""
    print("🔍 Enhanced Referrer Detection Test")
    print("=" * 40)
    
    # Test cases with different referrer sources
    test_cases = [
        {
            "name": "Website Domain Detection",
            "wa_id": "918309867100",
            "message": "Hi, I want to book an appointment",
            "referrer_url": "https://banjara.olivaclinics.com/contact",
            "expected_center": "Oliva Clinics Banjara Hills",
            "expected_location": "Hyderabad"
        },
        {
            "name": "UTM Parameters in Message",
            "wa_id": "918309867101", 
            "message": "utm_source=olivaclinics&utm_medium=website&utm_campaign=jubilee_hills&utm_content=hyderabad",
            "referrer_url": "",
            "expected_center": "Oliva Clinics Jubilee Hills",
            "expected_location": "Hyderabad"
        },
        {
            "name": "Center Name in Message",
            "wa_id": "918309867102",
            "message": "Hi, I want to book an appointment at Gachibowli center",
            "referrer_url": "",
            "expected_center": "Oliva Clinics Gachibowli", 
            "expected_location": "Hyderabad"
        },
        {
            "name": "Mumbai Center Detection",
            "wa_id": "918309867103",
            "message": "Hello, I need an appointment at Bandra center",
            "referrer_url": "https://bandra.olivaclinics.com/",
            "expected_center": "Oliva Clinics Bandra",
            "expected_location": "Mumbai"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing {test_case['name']}...")
        print(f"   📱 WA ID: {test_case['wa_id']}")
        print(f"   💬 Message: {test_case['message']}")
        print(f"   🌐 Referrer URL: {test_case['referrer_url']}")
        
        # Simulate webhook with referrer header
        webhook_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{
                            "wa_id": test_case["wa_id"],
                            "profile": {
                                "name": f"Test User {i}"
                            }
                        }],
                        "messages": [{
                            "from": test_case["wa_id"],
                            "id": f"enhanced_test_{i}",
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
        
        # Headers with referrer information
        headers = {
            "Content-Type": "application/json",
            "Referer": test_case["referrer_url"]
        }
        
        try:
            # Send webhook request
            response = requests.post(
                f"{BASE_URL}/ws/webhook",
                json=webhook_payload,
                headers=headers
            )
            
            print(f"   📡 Webhook Status: {response.status_code}")
            
            if response.status_code == 200:
                print("   ✅ Webhook processed successfully!")
                
                # Wait for processing
                import time
                time.sleep(2)
                
                # Check referrer tracking
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
                    print(f"      🌐 Referrer URL: {data['referrer_url']}")
                    
                    # Verify expected results
                    if (data['center_name'] == test_case['expected_center'] and 
                        data['location'] == test_case['expected_location']):
                        print("   ✅ Expected results matched!")
                    else:
                        print("   ❌ Expected results did not match!")
                        print(f"      Expected: {test_case['expected_center']}, {test_case['expected_location']}")
                        print(f"      Got: {data['center_name']}, {data['location']}")
                else:
                    print("   ❌ No referrer tracking found")
            else:
                print(f"   ❌ Webhook failed: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

def test_website_integration():
    """Test website integration scenarios"""
    print("\n🌐 Website Integration Test")
    print("=" * 35)
    
    # Test different website scenarios
    website_scenarios = [
        {
            "domain": "banjara.olivaclinics.com",
            "expected_center": "Oliva Clinics Banjara Hills",
            "expected_location": "Hyderabad"
        },
        {
            "domain": "jubilee.olivaclinics.com", 
            "expected_center": "Oliva Clinics Jubilee Hills",
            "expected_location": "Hyderabad"
        },
        {
            "domain": "gachibowli.olivaclinics.com",
            "expected_center": "Oliva Clinics Gachibowli",
            "expected_location": "Hyderabad"
        },
        {
            "domain": "bandra.olivaclinics.com",
            "expected_center": "Oliva Clinics Bandra",
            "expected_location": "Mumbai"
        }
    ]
    
    for i, scenario in enumerate(website_scenarios, 1):
        print(f"\n{i}. Testing {scenario['domain']}...")
        
        wa_id = f"91830986720{i}"
        webhook_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{
                            "wa_id": wa_id,
                            "profile": {"name": f"Website User {i}"}
                        }],
                        "messages": [{
                            "from": wa_id,
                            "id": f"website_test_{i}",
                            "timestamp": str(int(datetime.now().timestamp())),
                            "type": "text",
                            "text": {"body": "Hi, I want to book an appointment"}
                        }],
                        "metadata": {"display_phone_number": "917729992376"}
                    }
                }]
            }]
        }
        
        # Headers with website referrer
        headers = {
            "Content-Type": "application/json",
            "Referer": f"https://{scenario['domain']}/contact"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/ws/webhook",
                json=webhook_payload,
                headers=headers
            )
            
            if response.status_code == 200:
                print("   ✅ Webhook processed!")
                
                # Check results
                referrer_response = requests.get(
                    f"{BASE_URL}/referrer/{wa_id}",
                    headers={"accept": "application/json"}
                )
                
                if referrer_response.status_code == 200:
                    data = referrer_response.json()
                    print(f"   🏥 Center: {data['center_name']}")
                    print(f"   📍 Location: {data['location']}")
                    
                    if (data['center_name'] == scenario['expected_center'] and 
                        data['location'] == scenario['expected_location']):
                        print("   ✅ Website detection working!")
                    else:
                        print("   ❌ Website detection failed!")
                else:
                    print("   ❌ No referrer tracking found")
            else:
                print(f"   ❌ Webhook failed: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Enhanced Referrer Detection Test Suite")
    print("=" * 50)
    
    test_enhanced_referrer_detection()
    test_website_integration()
    
    print("\n🎉 Enhanced testing completed!")
    print("\n📋 Summary:")
    print("- Tested multiple referrer detection methods")
    print("- Tested website domain detection")
    print("- Tested UTM parameter detection")
    print("- Tested center name detection")
