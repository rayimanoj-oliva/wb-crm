#!/usr/bin/env python3
"""
Quick test script to check modify order functionality
Run this to verify the current state of orders and items
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import SessionLocal
from models.models import Order, OrderItem, Customer
from sqlalchemy.orm import joinedload

def test_modify_order_state(wa_id="918309866859"):
    """Test the current state of orders for a specific WhatsApp ID"""
    
    db = SessionLocal()
    try:
        # Get customer
        customer = db.query(Customer).filter(Customer.wa_id == wa_id).first()
        if not customer:
            print(f"❌ Customer with wa_id {wa_id} not found")
            return
        
        print(f"✅ Customer found: {customer.name} ({customer.wa_id})")
        
        # Get latest order
        latest_order = (
            db.query(Order)
            .filter(Order.customer_id == customer.id)
            .options(joinedload(Order.items))
            .order_by(Order.timestamp.desc())
            .first()
        )
        
        if not latest_order:
            print("❌ No orders found for this customer")
            return
        
        print(f"✅ Latest order found: {latest_order.id}")
        print(f"   - Timestamp: {latest_order.timestamp}")
        print(f"   - Modification started: {latest_order.modification_started_at}")
        print(f"   - Total items: {len(latest_order.items)}")
        
        # Separate items by modification status
        original_items = [item for item in latest_order.items if not item.is_modification_addition]
        new_items = [item for item in latest_order.items if item.is_modification_addition]
        
        print(f"\n📦 Original items ({len(original_items)}):")
        for item in original_items:
            print(f"   - {item.product_retailer_id} (qty: {item.quantity})")
        
        print(f"\n🆕 New items ({len(new_items)}):")
        for item in new_items:
            print(f"   - {item.product_retailer_id} (qty: {item.quantity})")
        
        # Check if modify order would work
        if latest_order.modification_started_at:
            print(f"\n✅ Order is in modification mode")
            print(f"   - Modification started: {latest_order.modification_started_at}")
        else:
            print(f"\n⚠️  Order is not in modification mode")
            print(f"   - This means modify order hasn't been clicked yet")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Test with default WA ID or provide one as argument
    wa_id = sys.argv[1] if len(sys.argv) > 1 else "918309866859"
    test_modify_order_state(wa_id)
