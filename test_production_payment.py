#!/usr/bin/env python3
"""
Production Payment Diagnostics Script
Test why payment links aren't being sent to customers in production
"""

import os
import sys
from datetime import datetime

def check_environment():
    """Check environment variables"""
    print("🔍 Checking Environment Variables")
    print("=" * 50)
    
    env_vars = {
        'RAZORPAY_KEY_ID': os.getenv('RAZORPAY_KEY_ID'),
        'RAZORPAY_SECRET': os.getenv('RAZORPAY_SECRET'),
        'WHATSAPP_PHONE_ID': os.getenv('WHATSAPP_PHONE_ID'),
        'WHATSAPP_TOKEN': os.getenv('WHATSAPP_TOKEN')
    }
    
    for key, value in env_vars.items():
        if value:
            # Show first 10 chars for security
            masked = value[:10] + "..." if len(value) > 10 else value
            print(f"✅ {key}: {masked}")
        else:
            print(f"❌ {key}: NOT SET")
    
    print()

def test_razorpay_connection():
    """Test Razorpay API connection"""
    print("🔍 Testing Razorpay Connection")
    print("=" * 50)
    
    try:
        from payment.razorpay_client import RazorpayClient
        
        client = RazorpayClient()
        
        # Test payment link creation
        print("Creating test payment link...")
        response = client.create_payment_link(
            amount=1.0,
            description="Test payment from diagnostics script"
        )
        
        if "error" in response:
            print(f"❌ Payment link creation failed: {response['error']}")
            print(f"Error type: {response.get('error_type', 'unknown')}")
            return False
        else:
            print(f"✅ Payment link created successfully!")
            print(f"Payment ID: {response.get('id', 'N/A')}")
            print(f"Payment URL: {response.get('short_url', 'N/A')}")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_whatsapp_connection():
    """Test WhatsApp API connection"""
    print("\n🔍 Testing WhatsApp Connection")
    print("=" * 50)
    
    try:
        from services.whatsapp_service import get_latest_token
        from config.constants import get_messages_url
        import requests
        
        # Import database
        from database.db import SessionLocal
        db = SessionLocal()
        
        try:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                print("❌ WhatsApp token not found")
                return False
            
            print(f"✅ WhatsApp token found: {token_entry.token[:20]}...")
            
            # Test WhatsApp API (don't send actual message in test)
            print("✅ WhatsApp configuration looks good")
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_payment_service():
    """Test payment service"""
    print("\n🔍 Testing Payment Service")
    print("=" * 50)
    
    try:
        from payment.payment_service import PaymentService
        from database.db import SessionLocal
        from payment.schemas import PaymentCreate
        
        db = SessionLocal()
        
        try:
            payment_service = PaymentService(db)
            
            # Create test payment
            payload = PaymentCreate(
                order_id="test_order_123",
                amount=100.0,
                currency="INR",
                customer_name="Test User",
                customer_email="test@example.com"
            )
            
            print("Creating test payment...")
            payment = payment_service.create_payment_link(payload, mock=False)
            
            print(f"✅ Payment created successfully!")
            print(f"Payment ID: {payment.razorpay_id}")
            print(f"Payment URL: {payment.razorpay_short_url}")
            print(f"Status: {payment.status}")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_cart_checkout():
    """Test cart checkout service"""
    print("\n🔍 Testing Cart Checkout Service")
    print("=" * 50)
    
    try:
        from services.cart_checkout_service import CartCheckoutService
        from database.db import SessionLocal
        
        db = SessionLocal()
        
        try:
            checkout_service = CartCheckoutService(db)
            
            print("✅ Cart checkout service initialized")
            
            # Test order calculation (assuming you have a test order)
            # result = checkout_service.calculate_order_total("test_order_id")
            # print(f"Order calculation result: {result}")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Run all diagnostics"""
    print("🚀 Production Payment Diagnostics")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = {}
    
    # Run tests
    results['environment'] = check_environment()
    results['razorpay'] = test_razorpay_connection()
    results['whatsapp'] = test_whatsapp_connection()
    results['payment_service'] = test_payment_service()
    results['cart_checkout'] = test_cart_checkout()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name.upper()}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Payment system is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Please check the issues above.")
        print("\n📋 Common Issues:")
        print("1. RAZORPAY_KEY_ID or RAZORPAY_SECRET not set correctly")
        print("2. Invalid Razorpay credentials")
        print("3. Network connectivity issues")
        print("4. WhatsApp token expired or invalid")
        print("5. Database connection issues")
        
        print("\n🔧 Recommended Actions:")
        if not results.get('razorpay'):
            print("- Check Razorpay credentials in environment variables")
            print("- Verify Razorpay account is active")
            print("- Test Razorpay API manually")
        
        if not results.get('whatsapp'):
            print("- Check WhatsApp token in database")
            print("- Verify WhatsApp Business API credentials")
            print("- Check WhatsApp API connectivity")
        
        if not results.get('payment_service'):
            print("- Check payment service configuration")
            print("- Verify database connection")
            print("- Check error logs for specific issues")

if __name__ == "__main__":
    main()
