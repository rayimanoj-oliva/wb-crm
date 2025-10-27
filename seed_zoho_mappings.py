"""
Seed script to populate initial Zoho mappings based on the user's mapping table
Run this once after creating the zoho_mappings table to populate initial data
"""

from database.db import SessionLocal
from services.zoho_mapping_service import create_zoho_mapping, get_zoho_mapping


def seed_zoho_mappings():
    """Populate Zoho mappings based on the treatment concerns to Zoho names mapping"""
    
    # Define the mappings based on the images provided
    mappings = [
        # Skin Concerns
        {"treatment_name": "Acne / Acne Scars", "zoho_name": "Acne", "zoho_sub_concern": "Pimple Treatment"},
        {"treatment_name": "Pigmentation & Uneven Skin Tone", "zoho_name": "Pigmentation", "zoho_sub_concern": "Pigmentation Treatment"},
        {"treatment_name": "Anti-Aging & Skin Rejuvenation", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Anti Aging"},
        {"treatment_name": "Laser Hair Removal", "zoho_name": "Unwanted Hair", "zoho_sub_concern": "Laser Hair Removal"},
        {"treatment_name": "Other Skin Concerns", "zoho_name": "Skin Cocnern", "zoho_sub_concern": None},
        
        # Hair Concerns
        {"treatment_name": "Hair Loss / Hair Fall", "zoho_name": "Hair", "zoho_sub_concern": "Hair Loss Treatment"},
        {"treatment_name": "Hair Transplant", "zoho_name": "Hair Transplantation", "zoho_sub_concern": "DHI / Hair Transplantation / Hair"},
        {"treatment_name": "Dandruff & Scalp Care", "zoho_name": "Hair", "zoho_sub_concern": "Dandruff"},
        {"treatment_name": "Other Hair Concerns", "zoho_name": "Hair", "zoho_sub_concern": None},
        
        # Body Concerns
        {"treatment_name": "Weight Management", "zoho_name": "Weight Loss", "zoho_sub_concern": "Weight Management"},
        {"treatment_name": "Body Contouring", "zoho_name": "Inch Loss Treatment", "zoho_sub_concern": "Fat Loss/Inch Loss"},
        {"treatment_name": "Weight Loss", "zoho_name": "Inch Loss Treatment", "zoho_sub_concern": "Weight Loss Treatment"},
        {"treatment_name": "Other Body Concerns", "zoho_name": "Weight Loss", "zoho_sub_concern": "Weight Loss"},
        
        # Additional detailed mappings based on the images
        {"treatment_name": "Acne Scar", "zoho_name": "SCAR", "zoho_sub_concern": "Acne Scar / Accidental scars / Burn Scars / Stretch Marks / Chicken pox scar"},
        {"treatment_name": "Skin whitening", "zoho_name": "Skin whitening", "zoho_sub_concern": "Skin Whitening"},
        {"treatment_name": "Dull Skin Treatment", "zoho_name": "Skin whitening", "zoho_sub_concern": "Dull Skin Treatment"},
        {"treatment_name": "Insta Glow Treatment", "zoho_name": "Skin whitening", "zoho_sub_concern": "Insta Glow Treatment"},
        {"treatment_name": "Black Peel Treatment", "zoho_name": "Acne", "zoho_sub_concern": "Black Peel Treatment"},
        {"treatment_name": "Botox Treatment", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Botox Treatment"},
        {"treatment_name": "Fillers Treatment", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Fillers Treatment"},
        {"treatment_name": "Stretch Marks Treatment", "zoho_name": "Scar", "zoho_sub_concern": "Stretch Marks"},
        {"treatment_name": "Anti Ageing", "zoho_name": "Anti Aeging", "zoho_sub_concern": "Anti ageging / Fine line / Wrinklkes"},
        {"treatment_name": "Hydrageneo Treatment", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Hydrageneo Treatment"},
        {"treatment_name": "Chin Sculpting Treatment", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Chin Sculpting Treatment"},
        {"treatment_name": "Moles Removal", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Moles Removal"},
        {"treatment_name": "Warts Removal", "zoho_name": "Skin Concerns", "zoho_sub_concern": "Warts Removal"},
        {"treatment_name": "Tattoo Removal", "zoho_name": "Tattoo", "zoho_sub_concern": "Tattoo"},
        {"treatment_name": "PRP Hair Treatment", "zoho_name": "Hair", "zoho_sub_concern": "PRP Hair Treatment"},
        {"treatment_name": "Hair Thread Treatment", "zoho_name": "Hair", "zoho_sub_concern": "Hair Thread Treatment"},
        {"treatment_name": "QR678", "zoho_name": "Hair", "zoho_sub_concern": "QR678"},
        {"treatment_name": "Warts / DPN", "zoho_name": "Warts", "zoho_sub_concern": "Warts / DPN"},
        {"treatment_name": "Skin Tags", "zoho_name": "Skin Tags", "zoho_sub_concern": "EC / RF"},
        {"treatment_name": "Beyond Weight loss", "zoho_name": "Weight Loss", "zoho_sub_concern": "Beyond Weight loss"},
        
        # Pigmentation related
        {"treatment_name": "Melasma", "zoho_name": "Pigmentation", "zoho_sub_concern": "Melasma"},
        {"treatment_name": "Dark circle", "zoho_name": "Dark Cirlce", "zoho_sub_concern": "Dark circle"},
        {"treatment_name": "Keloids", "zoho_name": "Skin", "zoho_sub_concern": "Keloids"},
        {"treatment_name": "Mark Removal", "zoho_name": "Marks", "zoho_sub_concern": "BirthMarks / Cut Marks / Marks / Sucidal Marks"},
        {"treatment_name": "Rashes / Allergy", "zoho_name": "Skin Cocnern", "zoho_sub_concern": "Rashes / Allergy"},
        {"treatment_name": "Corn", "zoho_name": "Other", "zoho_sub_concern": "Corn"},
        {"treatment_name": "Inch Loss", "zoho_name": "Inch Loss Treatment", "zoho_sub_concern": "Fat Loss/Inch Loss"},
        {"treatment_name": "Body Contouring", "zoho_name": "Inch Loss Treatment", "zoho_sub_concern": "Body Contouring"},
    ]
    
    db = SessionLocal()
    created_count = 0
    skipped_count = 0
    
    try:
        print("\nStarting to seed Zoho mappings...")
        
        for mapping in mappings:
            # Check if mapping already exists
            existing = get_zoho_mapping(db, mapping["treatment_name"])
            
            if existing:
                print(f"Skipping existing: {mapping['treatment_name']} -> {mapping['zoho_name']}")
                skipped_count += 1
            else:
                create_zoho_mapping(
                    db=db,
                    treatment_name=mapping["treatment_name"],
                    zoho_name=mapping["zoho_name"],
                    zoho_sub_concern=mapping.get("zoho_sub_concern")
                )
                print(f"Created: {mapping['treatment_name']} -> {mapping['zoho_name']}")
                created_count += 1
        
        db.commit()
        print("\nSeeding complete!")
        print(f"Created: {created_count} mappings")
        print(f"Skipped: {skipped_count} existing mappings")
        
    except Exception as e:
        print(f"\nError during seeding: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_zoho_mappings()

