"""Script to create flow_logs table directly"""

from database.db import engine
from sqlalchemy import text


def create_flow_logs_table():
    """Create flow_logs table in database"""

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS flow_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        wa_id VARCHAR(64),
        name VARCHAR(255),
        flow_type VARCHAR(50) NOT NULL,
        step VARCHAR(100),
        status_code INTEGER,
        description TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS ix_flow_logs_created_at ON flow_logs(created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_flow_logs_wa_id ON flow_logs(wa_id);
    CREATE INDEX IF NOT EXISTS ix_flow_logs_flow_type_created_at ON flow_logs(flow_type, created_at DESC);
    """

    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'flow_logs'
                );
            """))
            table_exists = result.scalar()

            if table_exists:
                print("✅ flow_logs table already exists")
            else:
                print("📝 Creating flow_logs table...")
                conn.execute(text(create_table_sql))
                conn.commit()
                print("✅ flow_logs table created successfully!")

                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'flow_logs';
                """))
                count = result.scalar()
                print(f"📊 Table has {count} columns")
        return True
    except Exception as e:
        print(f"❌ Error creating flow_logs table: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    create_flow_logs_table()


