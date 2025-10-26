#!/usr/bin/env python3
"""
Razorpay Configuration Checker
Check if Razorpay is properly configured and working
"""

import os
import sys
from datetime import datetime

def check_environment_variables():
    """Check if all required environment variables are set"""
    print("🔧 Checking Environment Variables")
    print("=" * 40)
    
    required_vars = {
        'RAZORPAY_KEY_ID': os.getenv('RAZORPAY_KEY_ID'),
        'RAZORPAY_SECRET': os.getenv('RAZORPAY_SECRET'),
        'RAZORPAY_WEBHOOK_SECRET': os.getenv('RAZORPAY_WEBHOOK_SECRET')
    }
    
    all_good = True
    
    for var_name, var_value in required_vars.items():
        if not var_value:
            print(f"❌ {var_name}: Not set")
            all_good = False
        elif var_value in ['rzp_test_123456789', 'test_secret_123456789', 'your_razorpay_webhook_secret']:
            print(f"⚠️  {var_name}: Using default/test value")
            all_good = False
        else:
            # Show first 10 characters for security
            masked_value = var_value[:10] + "..." if len(var_value) > 10 else var_value
            print(f"✅ {var_name}: {masked_value}")
    
    return all_good

def test_razorpay_client():
    """Test Razorpay client initialization and basic functionality"""
    print("\n🧪 Testing Razorpay Client")
    print("=" * 40)
    
    try:
        # Import the payment module
        from payment.razorpay_client import RazorpayClient
        
        # Initialize client
        client = RazorpayClient()
        print("✅ Razorpay client initialized successfully")
        
        # Test configuration status
        config_status = client.get_configuration_status()
        print(f"✅ Configuration status: {config_status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing Razorpay client: {e}")
        return False

def test_payment_creation():
    """Test payment link creation"""
    print("\n💳 Testing Payment Creation")
    print("=" * 40)
    
    try:
        from payment.razorpay_client import RazorpayClient
        
        client = RazorpayClient()
        
        # Test with minimal amount
        response = client.create_payment_link(
            amount=1.0,
            description="Test payment from configuration checker",
            customer_name="Test User",
            customer_email="test@example.com"
        )
        
        if "error" in response:
            print(f"❌ Payment creation failed: {response['error']}")
            return False
        else:
            print(f"✅ Payment link created successfully!")
            print(f"   Payment ID: {response.get('id', 'N/A')}")
            print(f"   Payment URL: {response.get('short_url', 'N/A')}")
            print(f"   Status: {response.get('status', 'N/A')}")
            return True
            
    except Exception as e:
        print(f"❌ Error creating payment: {e}")
        return False

def test_webhook_signature():
    """Test webhook signature validation"""
    print("\n🔐 Testing Webhook Signature Validation")
    print("=" * 40)
    
    try:
        import hmac
        import hashlib
        from payment.razorpay_client import RazorpayClient
        
        client = RazorpayClient()
        
        # Test data
        test_data = b'{"event":"payment.captured","created_at":1640995200}'
        test_secret = "test_webhook_secret_123"
        
        # Generate signature
        generated_signature = hmac.new(
            bytes(test_secret, 'utf-8'),
            msg=test_data,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Test validation
        result = client.validate_webhook_signature(test_data, generated_signature, test_secret)
        
        if result:
            print("✅ Webhook signature validation working correctly")
            return True
        else:
            print("❌ Webhook signature validation failed")
            return False
            
    except Exception as e:
        print(f"❌ Error testing webhook signature: {e}")
        return False

def test_diagnostics_endpoint():
    """Test diagnostics endpoint (if server is running)"""
    print("\n🔍 Testing Diagnostics Endpoint")
    print("=" * 40)
    
    try:
        import requests
        
        # Try to reach diagnostics endpoint
        response = requests.get("http://localhost:8000/payments/diagnostics", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Diagnostics endpoint accessible")
            print(f"   Razorpay config: {data.get('razorpay_config', {})}")
            print(f"   API test: {data.get('api_test', {})}")
            return True
        else:
            print(f"⚠️  Diagnostics endpoint returned status: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  Server not running or diagnostics endpoint not accessible")
        print("   Start your server and try: curl -X GET 'http://localhost:8000/payments/diagnostics'")
        return False
    except Exception as e:
        print(f"❌ Error testing diagnostics endpoint: {e}")
        return False

def main():
    """Main function to run all tests"""
    print("🚀 Razorpay Configuration Checker")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Run all tests
    tests = [
        ("Environment Variables", check_environment_variables),
        ("Razorpay Client", test_razorpay_client),
        ("Payment Creation", test_payment_creation),
        ("Webhook Signature", test_webhook_signature),
        ("Diagnostics Endpoint", test_diagnostics_endpoint)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 40)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Razorpay is properly configured.")
    else:
        print("\n⚠️  Some tests failed. Please check the issues above.")
        print("\n📋 Next Steps:")
        print("1. Set missing environment variables")
        print("2. Verify Razorpay credentials")
        print("3. Check Razorpay dashboard configuration")
        print("4. Review the integration guide: RAZORPAY_INTEGRATION_GUIDE.md")

if __name__ == "__main__":
    main()
