"""
Test script for the new address collection system
Demonstrates the JioMart/Blinkit/Domino's style address collection
"""

import asyncio
import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session
from database.db import SessionLocal
from services.address_collection_service import AddressCollectionService
from services.address_service import create_customer_address, get_customer_addresses
from schemas.address_schema import CustomerAddressCreate
from models.models import Customer


def create_test_customer(db: Session) -> Customer:
    """Create a test customer for testing"""
    from services.customer_service import get_or_create_customer
    from schemas.customer_schema import CustomerCreate
    
    customer_data = CustomerCreate(wa_id="919876543210", name="Test Customer")
    return get_or_create_customer(db, customer_data)


async def test_address_collection_flow():
    """Test the complete address collection flow"""
    print("🧪 Testing New Address Collection System")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # Create test customer
        customer = create_test_customer(db)
        print(f"✅ Created test customer: {customer.name} ({customer.wa_id})")
        
        # Initialize address collection service
        address_service = AddressCollectionService(db)
        
        # Test 1: Start address collection after order
        print("\n📦 Test 1: Starting address collection after order")
        order_items = [
            {"product_retailer_id": "123", "quantity": 2, "item_price": 100, "currency": "INR"},
            {"product_retailer_id": "456", "quantity": 1, "item_price": 200, "currency": "INR"}
        ]
        
        result = await address_service.start_address_collection_after_order(
            wa_id=customer.wa_id,
            order_id=uuid4(),
            customer_name=customer.name,
            order_total=400.0,
            order_items=order_items
        )
        
        print(f"   Result: {result}")
        
        # Test 2: Handle address button clicks
        print("\n🔘 Test 2: Handling address button clicks")
        
        # Test "Add Delivery Address" button
        result = await address_service.handle_address_button_click(
            wa_id=customer.wa_id,
            button_payload="ADD_DELIVERY_ADDRESS"
        )
        print(f"   ADD_DELIVERY_ADDRESS: {result}")
        
        # Test 3: Manual address entry
        print("\n📝 Test 3: Manual address entry")
        address_text = """
        Full Name: John Doe
        House Street: 123 Main Street
        Locality: Downtown
        City: Mumbai
        State: Maharashtra
        Pincode: 400001
        Phone: 9876543210
        Landmark: Near Metro Station
        """
        
        result = await address_service.handle_manual_address_text(
            wa_id=customer.wa_id,
            address_text=address_text
        )
        print(f"   Manual address result: {result}")
        
        # Test 4: Location-based address
        print("\n📍 Test 4: Location-based address")
        result = await address_service.handle_location_message(
            wa_id=customer.wa_id,
            latitude=19.0760,
            longitude=72.8777,
            location_name="Gateway of India",
            location_address="Apollo Bunder, Colaba, Mumbai"
        )
        print(f"   Location address result: {result}")
        
        # Test 5: Check saved addresses
        print("\n💾 Test 5: Check saved addresses")
        addresses = get_customer_addresses(db, customer.id)
        print(f"   Found {len(addresses)} saved addresses:")
        for i, addr in enumerate(addresses, 1):
            print(f"   {i}. {addr.full_name}, {addr.house_street}, {addr.city} - {addr.pincode}")
        
        # Test 6: Address validation
        print("\n✅ Test 6: Address validation")
        from services.address_service import validate_address_data
        
        test_address = {
            "full_name": "Jane Smith",
            "house_street": "456 Oak Avenue",
            "locality": "Suburb",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110001",
            "phone": "9876543210",
            "landmark": "Near Park"
        }
        
        validation_result = validate_address_data(test_address)
        print(f"   Validation result: {validation_result}")
        
        print("\n🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()


def test_address_api_endpoints():
    """Test the address API endpoints"""
    print("\n🌐 Testing Address API Endpoints")
    print("=" * 50)
    
    # This would typically be done with actual HTTP requests
    # For now, we'll just show the available endpoints
    
    endpoints = [
        "POST /address/ - Create new address",
        "GET /address/customer/{customer_id} - Get customer addresses",
        "GET /address/customer/{customer_id}/default - Get default address",
        "PUT /address/{address_id} - Update address",
        "DELETE /address/{address_id} - Delete address",
        "POST /address/collection/session - Create collection session",
        "GET /address/collection/session/{session_id} - Get session",
        "PUT /address/collection/session/{session_id} - Update session",
        "POST /address/collection/session/{session_id}/complete - Complete session",
        "POST /address/validate - Validate address",
        "POST /address/quick - Create quick address",
        "GET /address/options/{customer_id} - Get collection options",
        "POST /address/cleanup - Cleanup expired sessions"
    ]
    
    for endpoint in endpoints:
        print(f"   {endpoint}")


def demonstrate_whatsapp_templates():
    """Demonstrate the WhatsApp templates"""
    print("\n📱 WhatsApp Templates for Address Collection")
    print("=" * 50)
    
    from utils.address_templates import (
        get_order_confirmation_template,
        get_address_collection_options_template,
        get_location_request_template,
        get_manual_address_template,
        get_address_confirmation_template
    )
    
    # Order confirmation template
    order_template = get_order_confirmation_template(
        customer_name="John Doe",
        order_total=400.0,
        order_items=[{"name": "Product 1", "price": 200}, {"name": "Product 2", "price": 200}]
    )
    print("1. Order Confirmation Template:")
    print(json.dumps(order_template, indent=2))
    
    # Address options template
    options_template = get_address_collection_options_template(
        customer_name="John Doe",
        has_saved_addresses=True
    )
    print("\n2. Address Collection Options Template:")
    print(json.dumps(options_template, indent=2))
    
    # Location request template
    location_template = get_location_request_template()
    print("\n3. Location Request Template:")
    print(json.dumps(location_template, indent=2))
    
    # Manual address template
    manual_template = get_manual_address_template()
    print("\n4. Manual Address Template:")
    print(json.dumps(manual_template, indent=2))


async def main():
    """Main test function"""
    print("🚀 New Address Collection System - Test Suite")
    print("=" * 60)
    print("This test demonstrates the JioMart/Blinkit/Domino's style")
    print("address collection system implementation.")
    print("=" * 60)
    
    # Run the main address collection flow test
    await test_address_collection_flow()
    
    # Show API endpoints
    test_address_api_endpoints()
    
    # Demonstrate templates
    demonstrate_whatsapp_templates()
    
    print("\n" + "=" * 60)
    print("✅ Test suite completed!")
    print("\nNext steps:")
    print("1. Run database migration: python -m alembic upgrade head")
    print("2. Create WhatsApp templates in Meta Business Manager")
    print("3. Test with real WhatsApp messages")
    print("4. Monitor address collection success rates")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
