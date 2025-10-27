"""
Script to check if Zoho mappings are properly saved and can be retrieved
"""

from database.db import SessionLocal
from services.zoho_mapping_service import get_zoho_mapping, get_zoho_name, list_all_mappings
from sqlalchemy import text


def check_zoho_mappings():
    """Check if Zoho mappings exist in database"""
    
    db = SessionLocal()
    
    try:
        print("\n=== Checking Zoho Mappings Database ===")
        
        # Check if table exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'zoho_mappings'
            );
        """))
        table_exists = result.scalar()
        print(f"\n1. Table 'zoho_mappings' exists: {table_exists}")
        
        # Get count of mappings
        result = db.execute(text("SELECT COUNT(*) FROM zoho_mappings;"))
        count = result.scalar()
        print(f"2. Total mappings in database: {count}")
        
        # List all mappings
        all_mappings = list_all_mappings(db)
        print(f"\n3. Sample of first 10 mappings:")
        for i, mapping in enumerate(all_mappings[:10], 1):
            print(f"   {i}. {mapping.treatment_name} -> {mapping.zoho_name}")
        
        # Test some specific lookups
        print(f"\n4. Testing specific lookups:")
        test_concerns = [
            "Acne / Acne Scars",
            "Pigmentation & Uneven Skin Tone",
            "Hair Loss / Hair Fall",
            "Weight Management"
        ]
        
        for concern in test_concerns:
            zoho_name = get_zoho_name(db, concern)
            print(f"   - '{concern}' -> '{zoho_name}'")
        
        # Check table structure
        result = db.execute(text("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns 
            WHERE table_name = 'zoho_mappings'
            ORDER BY ordinal_position;
        """))
        print(f"\n5. Table structure:")
        for row in result:
            print(f"   - {row.column_name}: {row.data_type}" + 
                  (f"({row.character_maximum_length})" if row.character_maximum_length else ""))
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    check_zoho_mappings()

