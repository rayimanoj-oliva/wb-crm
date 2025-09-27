#!/usr/bin/env python3
"""
Local testing script for referrer tracking
"""
import requests
import json
from datetime import datetime
import time

BASE_URL = "http://127.0.0.1:8000"

def test_referrer_tracking():
    """Test referrer tracking functionality locally"""
    print("🧪 Local Referrer Tracking Test")
    print("=" * 40)
    
    # Test data for different centers
    test_cases = [
        {
            "wa_id": "918309866900",
            "center": "Banjara Hills",
            "utm_campaign": "banjara_hills",
            "location": "Hyderabad",
            "referrer_url": "https://banjara.olivaclinics.com/contact"
        },
        {
            "wa_id": "918309866901", 
            "center": "Jubilee Hills",
            "utm_campaign": "jubilee_hills",
            "location": "Hyderabad",
            "referrer_url": "https://jubilee.olivaclinics.com/"
        },
        {
            "wa_id": "918309866902",
            "center": "Bandra",
            "utm_campaign": "mumbai_bandra", 
            "location": "Mumbai",
            "referrer_url": "https://bandra.olivaclinics.com/"
        },
        {
            "wa_id": "918309866903",
            "center": "Gachibowli",
            "utm_campaign": "gachibowli",
            "location": "Hyderabad", 
            "referrer_url": "https://gachibowli.olivaclinics.com/"
        }
    ]
    
    print("📝 Creating referrer tracking records...")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing {test_case['center']} center...")
        
        # Create referrer tracking record
        referrer_data = {
            "wa_id": test_case["wa_id"],
            "utm_source": "olivaclinics",
            "utm_medium": "website",
            "utm_campaign": test_case["utm_campaign"],
            "utm_content": test_case["location"].lower(),
            "referrer_url": test_case["referrer_url"],
            "center_name": f"Oliva Clinics {test_case['center']}",
            "location": test_case["location"]
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/referrer/track",
                json=referrer_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                print(f"✅ {test_case['center']} - Referrer tracking created")
                
                # Verify the record was created
                verify_response = requests.get(
                    f"{BASE_URL}/referrer/{test_case['wa_id']}",
                    headers={"accept": "application/json"}
                )
                
                if verify_response.status_code == 200:
                    data = verify_response.json()
                    print(f"   Center: {data['center_name']}")
                    print(f"   Location: {data['location']}")
                    print(f"   UTM Campaign: {data['utm_campaign']}")
                else:
                    print(f"   ❌ Verification failed: {verify_response.text}")
            else:
                print(f"❌ {test_case['center']} - Failed: {response.text}")
                
        except Exception as e:
            print(f"❌ {test_case['center']} - Error: {e}")
    
    print(f"\n📊 Summary: Tested {len(test_cases)} centers")

def test_appointment_booking():
    """Test appointment booking with center information"""
    print("\n📅 Testing Appointment Booking Flow")
    print("=" * 40)
    
    # Test with Banjara Hills user
    wa_id = "918309866900"
    
    print(f"Testing appointment booking for {wa_id}...")
    
    # Simulate appointment booking webhook
    appointment_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{
                        "wa_id": wa_id,
                        "profile": {
                            "name": "Test User"
                        }
                    }],
                    "messages": [{
                        "from": wa_id,
                        "id": "appointment_test_123",
                        "timestamp": str(int(datetime.now().timestamp())),
                        "type": "text",
                        "text": {
                            "body": "book appointment"
                        }
                    }],
                    "metadata": {
                        "display_phone_number": "917729992376"
                    }
                }
            }]
        }]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/ws/webhook",
            json=appointment_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Appointment booking response: {response.status_code}")
        if response.status_code == 200:
            print("✅ Appointment booking webhook processed!")
        else:
            print(f"❌ Appointment booking failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error in appointment booking: {e}")

def get_all_referrers():
    """Get all referrer tracking records"""
    print("\n📋 All Referrer Records")
    print("=" * 30)
    
    try:
        response = requests.get(
            f"{BASE_URL}/referrer/",
            headers={"accept": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total records: {len(data)}")
            
            for record in data:
                print(f"\n📱 WA ID: {record['wa_id']}")
                print(f"   Center: {record['center_name']}")
                print(f"   Location: {record['location']}")
                print(f"   UTM Campaign: {record['utm_campaign']}")
                print(f"   Created: {record['created_at']}")
        else:
            print(f"❌ Failed to get referrer records: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Local Referrer Tracking Test Suite")
    print("=" * 50)
    
    test_referrer_tracking()
    test_appointment_booking()
    get_all_referrers()
    
    print("\n🎉 Local testing completed!")
    print("\n📋 Next Steps:")
    print("1. Check your database for referrer records")
    print("2. Test appointment confirmations include center info")
    print("3. Use the online testing setup for real website testing")
