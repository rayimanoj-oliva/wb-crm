#!/usr/bin/env python3
"""
Test script for the fixed cart checkout flow
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import get_db
from services.cart_checkout_service import CartCheckoutService

async def test_cart_checkout():
    """Test the cart checkout flow"""
    print("🧪 Testing Cart Checkout Flow...")
    
    # Get database session
    db = next(get_db())
    
    try:
        # Create checkout service
        checkout_service = CartCheckoutService(db)
        
        # Test order ID (you'll need to replace this with a real order ID)
        test_order_id = "your_test_order_id_here"
        test_wa_id = "919876543210"
        test_customer_name = "Test Customer"
        
        print(f"📦 Testing with Order ID: {test_order_id}")
        print(f"📱 Testing with WA ID: {test_wa_id}")
        
        # Test order calculation
        print("\n1️⃣ Testing order calculation...")
        order_calculation = checkout_service.calculate_order_total(test_order_id)
        print(f"Order calculation result: {order_calculation}")
        
        if "error" in order_calculation:
            print(f"❌ Order calculation failed: {order_calculation['error']}")
            print("💡 Make sure you have a valid order ID in the database")
            return
        
        # Test payment link generation
        print("\n2️⃣ Testing payment link generation...")
        payment_result = await checkout_service.generate_payment_link_for_order(
            order_id=test_order_id,
            customer_wa_id=test_wa_id,
            customer_name=test_customer_name,
            customer_email="test@example.com",
            customer_phone="9876543210"
        )
        
        print(f"Payment result: {payment_result}")
        
        if payment_result.get("success"):
            print("✅ Payment link generated successfully!")
            print(f"🔗 Payment URL: {payment_result.get('payment_url')}")
            print(f"💰 Order Total: ₹{payment_result.get('order_total')}")
        else:
            print(f"❌ Payment generation failed: {payment_result.get('error')}")
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Starting Cart Checkout Test...")
    asyncio.run(test_cart_checkout())
    print("\n✅ Test completed!")
