"""
Test script to verify Zoho name mapping during lead creation
"""

from database.db import SessionLocal
from sqlalchemy.orm import Session
from controllers.web_socket import appointment_state
from models.models import Customer
import uuid


def test_lead_creation_mapping():
    """Test if Zoho mapping is applied during lead creation"""
    
    db = SessionLocal()
    
    try:
        print("\n=== Testing Lead Creation with Zoho Mapping ===\n")
        
        # Import the lead creation function
        from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
        from services.zoho_mapping_service import get_zoho_name
        from services.customer_service import get_customer_record_by_wa_id
        
        # Test mapping lookup
        print("1. Testing Zoho name lookup for selected concerns:")
        test_concerns = [
            "Acne / Acne Scars",
            "Pigmentation & Uneven Skin Tone",
            "Anti-Aging & Skin Rejuvenation",
            "Laser Hair Removal",
            "Weight Management",
            "Hair Loss / Hair Fall"
        ]
        
        for concern in test_concerns:
            zoho_name = get_zoho_name(db, concern)
            print(f"   - Selected: '{concern}'")
            print(f"     Mapped to: '{zoho_name}'")
            print()
        
        # Simulate appointment state with selected concern
        print("2. Simulating appointment state with selected concern:")
        test_wa_id = "+911234567890"
        
        # Clear any existing state
        if test_wa_id in appointment_state:
            del appointment_state[test_wa_id]
        
        # Set up test state with a selected concern
        appointment_state[test_wa_id] = {
            "selected_concern": "Acne / Acne Scars"
        }
        
        print(f"   Created state for {test_wa_id}")
        print(f"   Stored concern: 'Acne / Acne Scars'")
        
        # Now test the lookup in appointment_state
        concern_data = appointment_state.get(test_wa_id, {})
        selected_concern = concern_data.get("selected_concern")
        
        if selected_concern:
            zoho_mapped = get_zoho_name(db, selected_concern)
            print(f"\n   Retrieved concern from state: '{selected_concern}'")
            print(f"   Mapped to Zoho name: '{zoho_mapped}'")
        else:
            print("   No concern found in state")
        
        # Check what gets saved in lead description
        print("\n3. What would be saved in lead description:")
        if selected_concern:
            zoho_mapped = get_zoho_name(db, selected_concern)
            description = f"Treatment/Zoho Concern: {zoho_mapped}"
            print(f"   Description field: '{description}'")
        
        print("\n=== Test Complete ===\n")
        
        # Clean up
        if test_wa_id in appointment_state:
            del appointment_state[test_wa_id]
            
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_lead_creation_mapping()

