#!/usr/bin/env python3
"""
Quick script to fix the follow_up_step column issue.
This drops the unused columns from the customers table.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

# Get database connection
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

print("=" * 60)
print("🔧 Fixing follow_up_step column issue")
print("=" * 60)

try:
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if columns exist
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'customers' 
            AND column_name IN ('follow_up_step', 'follow_up_status')
        """)
        
        result = conn.execute(check_query)
        existing_columns = [row[0] for row in result]
        
        if not existing_columns:
            print("✅ Columns 'follow_up_step' and 'follow_up_status' do not exist.")
            print("✅ No fix needed!")
        else:
            print(f"📋 Found columns: {', '.join(existing_columns)}")
            print("🗑️  Dropping columns...")
            
            # Drop columns
            for col in existing_columns:
                try:
                    drop_query = text(f"ALTER TABLE customers DROP COLUMN IF EXISTS {col}")
                    conn.execute(drop_query)
                    print(f"   ✅ Dropped column: {col}")
                except Exception as e:
                    print(f"   ❌ Error dropping {col}: {e}")
            
            # Commit the transaction
            conn.commit()
            print("\n✅ Successfully fixed the database!")
            print("✅ You can now create customers without errors.")
    
    print("\n" + "=" * 60)
    print("🎉 All done! Restart your FastAPI server and try again.")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ Error connecting to database: {e}")
    print("\n💡 Make sure your .env file has correct database credentials:")
    print("   POSTGRES_USER=your_user")
    print("   POSTGRES_PASSWORD=your_password")
    print("   POSTGRES_HOST=localhost")
    print("   POSTGRES_PORT=5432")
    print("   POSTGRES_DB=your_database")
    exit(1)

