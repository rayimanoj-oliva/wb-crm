"""Script to create leads table directly"""

from database.db import engine
from sqlalchemy import text

def create_leads_table():
    """Create leads table in database"""
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS leads (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        zoho_lead_id VARCHAR UNIQUE NOT NULL,
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100),
        email VARCHAR(255),
        phone VARCHAR(20) NOT NULL,
        mobile VARCHAR(20),
        city VARCHAR(100),
        lead_source VARCHAR(100),
        lead_status VARCHAR(50),
        company VARCHAR(100),
        description TEXT,
        wa_id VARCHAR NOT NULL,
        customer_id UUID,
        appointment_details JSONB,
        treatment_name VARCHAR(255),
        zoho_mapped_concern VARCHAR(255),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS ix_leads_zoho_lead_id ON leads(zoho_lead_id);
    CREATE INDEX IF NOT EXISTS ix_leads_wa_id ON leads(wa_id);
    CREATE INDEX IF NOT EXISTS ix_leads_phone ON leads(phone);
    """
    
    try:
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'leads'
                );
            """))
            table_exists = result.scalar()
            
            if table_exists:
                print("✅ Leads table already exists")
            else:
                print("📝 Creating leads table...")
                conn.execute(text(create_table_sql))
                conn.commit()
                print("✅ Leads table created successfully!")
                
                # Verify creation
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'leads';
                """))
                count = result.scalar()
                print(f"📊 Table has {count} columns")
        return True
    except Exception as e:
        print(f"❌ Error creating leads table: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_leads_table()

