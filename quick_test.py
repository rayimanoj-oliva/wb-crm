#!/usr/bin/env python3
"""
Quick test script for referrer tracking
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def quick_test():
    """Quick test of referrer tracking system"""
    print("⚡ Quick Referrer Tracking Test")
    print("=" * 35)
    
    # Test data
    test_data = {
        "wa_id": "918309866999",
        "utm_source": "olivaclinics",
        "utm_medium": "website",
        "utm_campaign": "banjara_hills",
        "utm_content": "hyderabad",
        "referrer_url": "https://banjara.olivaclinics.com/contact",
        "center_name": "Oliva Clinics Banjara Hills",
        "location": "Hyderabad"
    }
    
    print("1️⃣ Creating referrer tracking record...")
    try:
        response = requests.post(
            f"{BASE_URL}/referrer/track",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            print("✅ Referrer tracking created successfully!")
        else:
            print(f"❌ Failed: {response.text}")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    print("\n2️⃣ Verifying referrer tracking...")
    try:
        response = requests.get(
            f"{BASE_URL}/referrer/{test_data['wa_id']}",
            headers={"accept": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Referrer tracking verified!")
            print(f"   🏥 Center: {data['center_name']}")
            print(f"   📍 Location: {data['location']}")
            print(f"   🏷️  UTM Campaign: {data['utm_campaign']}")
        else:
            print(f"❌ Verification failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n3️⃣ Checking all referrer records...")
    try:
        response = requests.get(
            f"{BASE_URL}/referrer/",
            headers={"accept": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {len(data)} referrer tracking records")
        else:
            print(f"❌ Failed to get records: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n🎉 Quick test completed!")
    print("\n📋 Next steps:")
    print("1. Open test_online_referrer.html in your browser")
    print("2. Click WhatsApp buttons to test real website integration")
    print("3. Run 'python monitor_referrer.py' to monitor activity")

if __name__ == "__main__":
    quick_test()
