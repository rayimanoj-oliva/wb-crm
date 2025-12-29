"""
Script to map existing WhatsApp numbers to Oliva organization
Run this script once to migrate existing WhatsApp numbers to the database
"""
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import SessionLocal
from models.models import Organization, WhatsAppNumber
from marketing.whatsapp_numbers import WHATSAPP_NUMBERS
from sqlalchemy.exc import IntegrityError


def map_whatsapp_numbers_to_oliva():
    """Map existing WhatsApp numbers to Oliva organization"""
    db = SessionLocal()
    
    try:
        # Find Oliva organization by name (try multiple variations)
        oliva_names = [
            "Oliva Skin Hair Body Clinic",
            "Oliva",
            "oliva",
            "Oliva Clinic"
        ]
        
        oliva_org = None
        for name in oliva_names:
            oliva_org = db.query(Organization).filter(
                Organization.name.ilike(f"%{name}%")
            ).first()
            if oliva_org:
                print(f"Found organization: {oliva_org.name} (ID: {oliva_org.id})")
                break
        
        if not oliva_org:
            # Try to find by slug
            oliva_org = db.query(Organization).filter(
                Organization.slug.ilike("%oliva%")
            ).first()
        
        if not oliva_org:
            print("ERROR: Could not find Oliva organization in database.")
            print("Please create the organization first or update the script with the correct organization name.")
            return
        
        print(f"\nMapping WhatsApp numbers to organization: {oliva_org.name}")
        print(f"Organization ID: {oliva_org.id}\n")
        
        # Map each WhatsApp number from whatsapp_numbers.py
        mapped_count = 0
        skipped_count = 0
        
        for phone_id, config in WHATSAPP_NUMBERS.items():
            display_number = config.get("name", "")
            access_token = config.get("token", "")
            
            # Check if this number already exists
            existing = db.query(WhatsAppNumber).filter(
                WhatsAppNumber.phone_number_id == phone_id
            ).first()
            
            if existing:
                # Always update to ensure it's mapped to Oliva
                updated = False
                if existing.organization_id != oliva_org.id:
                    existing.organization_id = oliva_org.id
                    updated = True
                # Update other fields if needed
                if existing.display_number != display_number:
                    existing.display_number = display_number
                    updated = True
                if existing.access_token != access_token:
                    existing.access_token = access_token
                    updated = True
                
                if updated:
                    db.commit()
                    print(f"UPDATED: Phone ID {phone_id} ({display_number}) -> mapped to {oliva_org.name}")
                    mapped_count += 1
                else:
                    print(f"OK: Phone ID {phone_id} ({display_number}) already mapped to {oliva_org.name}")
                    skipped_count += 1
                continue
            
            # Determine webhook path based on phone number (you can customize this logic)
            # For now, use /webhook for the first number, /webhook2 for others
            webhook_path = "/webhook"  # Default
            
            try:
                whatsapp_number = WhatsAppNumber(
                    phone_number_id=phone_id,
                    display_number=display_number,
                    access_token=access_token,
                    webhook_path=webhook_path,
                    organization_id=oliva_org.id,
                    is_active=True
                )
                db.add(whatsapp_number)
                db.commit()
                db.refresh(whatsapp_number)
                print(f"SUCCESS: Mapped Phone ID {phone_id} ({display_number}) -> {oliva_org.name}")
                mapped_count += 1
            except IntegrityError as e:
                db.rollback()
                print(f"ERROR: Failed to map {phone_id}: {e}")
            except Exception as e:
                db.rollback()
                print(f"ERROR: Failed to map {phone_id}: {e}")
        
        print(f"\n=== Summary ===")
        print(f"Mapped: {mapped_count} new WhatsApp numbers")
        print(f"Skipped: {skipped_count} existing WhatsApp numbers")
        print(f"Total: {len(WHATSAPP_NUMBERS)} WhatsApp numbers processed")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("Mapping existing WhatsApp numbers to Oliva organization...")
    print("=" * 60)
    map_whatsapp_numbers_to_oliva()

