#!/usr/bin/env python3
"""
Simple test for cart checkout functionality
"""

import requests
import json

def test_cart_checkout_endpoint():
    """Test the cart checkout endpoint"""
    print("🧪 Testing Cart Checkout Endpoint...")
    
    # Test data
    test_data = {
        "order_id": "test_order_123",
        "customer_wa_id": "919876543210",
        "customer_name": "Test Customer",
        "customer_email": "test@example.com",
        "customer_phone": "9876543210"
    }
    
    try:
        # Test the endpoint
        response = requests.post(
            "http://localhost:8000/cart/checkout",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"📡 Response Status: {response.status_code}")
        print(f"📄 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("✅ Cart checkout endpoint is working!")
            print(f"📋 Response: {response.json()}")
        else:
            print(f"❌ Cart checkout failed with status {response.status_code}")
            print(f"📄 Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure the server is running on port 8000")
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_cart_checkout_endpoint()
