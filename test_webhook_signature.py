#!/usr/bin/env python3
"""
Webhook Signature Test Script
Test Razorpay webhook signature validation
"""

import hmac
import hashlib
import json
from payment.razorpay_client import RazorpayClient

def test_webhook_signature():
    """Test webhook signature validation"""
    
    # Test data
    test_data = b'{"event":"payment.captured","created_at":1640995200,"payload":{"payment":{"entity":{"id":"pay_test123","amount":10000,"currency":"INR","status":"captured"}}}}'
    test_secret = "test_webhook_secret_123"
    
    # Generate signature
    generated_signature = hmac.new(
        bytes(test_secret, 'utf-8'),
        msg=test_data,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    print(f"Test Data: {test_data}")
    print(f"Test Secret: {test_secret}")
    print(f"Generated Signature: {generated_signature}")
    
    # Test with RazorpayClient
    try:
        client = RazorpayClient()
        
        # Test with correct signature
        result1 = client.validate_webhook_signature(test_data, generated_signature, test_secret)
        print(f"✅ Correct signature validation: {result1}")
        
        # Test with wrong signature
        wrong_signature = "wrong_signature_123"
        result2 = client.validate_webhook_signature(test_data, wrong_signature, test_secret)
        print(f"❌ Wrong signature validation: {result2}")
        
        # Test with None signature
        result3 = client.validate_webhook_signature(test_data, None, test_secret)
        print(f"❌ None signature validation: {result3}")
        
        # Test with None secret
        result4 = client.validate_webhook_signature(test_data, generated_signature, None)
        print(f"❌ None secret validation: {result4}")
        
        # Test with empty data
        result5 = client.validate_webhook_signature(b'', generated_signature, test_secret)
        print(f"❌ Empty data validation: {result5}")
        
    except Exception as e:
        print(f"❌ Error testing webhook signature: {e}")

def test_environment_configuration():
    """Test environment configuration"""
    import os
    
    print("\n🔧 Environment Configuration Check:")
    print(f"RAZORPAY_KEY_ID: {'✅ Configured' if os.getenv('RAZORPAY_KEY_ID') and os.getenv('RAZORPAY_KEY_ID') != 'rzp_test_123456789' else '❌ Not configured'}")
    print(f"RAZORPAY_SECRET: {'✅ Configured' if os.getenv('RAZORPAY_SECRET') and os.getenv('RAZORPAY_SECRET') != 'test_secret_123456789' else '❌ Not configured'}")
    print(f"RAZORPAY_WEBHOOK_SECRET: {'✅ Configured' if os.getenv('RAZORPAY_WEBHOOK_SECRET') and os.getenv('RAZORPAY_WEBHOOK_SECRET') != 'your_razorpay_webhook_secret' else '❌ Not configured'}")

if __name__ == "__main__":
    print("🧪 Testing Razorpay Webhook Signature Validation")
    print("=" * 50)
    
    test_webhook_signature()
    test_environment_configuration()
    
    print("\n📋 Troubleshooting Tips:")
    print("1. Ensure RAZORPAY_WEBHOOK_SECRET is set in environment variables")
    print("2. Check that X-Razorpay-Signature header is present in webhook requests")
    print("3. Verify webhook secret matches the one configured in Razorpay dashboard")
    print("4. Test with diagnostics endpoint: GET /payments/diagnostics")
    print("5. Check application logs for detailed error messages")
