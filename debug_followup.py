#!/usr/bin/env python3
"""
Debug script to check follow-up status in production database
Run this on your production server to see what's happening with follow-ups
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Load environment variables
load_dotenv()

# Get database connection
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

print("=" * 70)
print("🔍 Follow-Up Debug Tool")
print("=" * 70)

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    from models.models import Customer
    
    # Current time
    now = datetime.utcnow()
    print(f"\n📅 Current UTC Time: {now}")
    print(f"📅 Current Local Time: {datetime.now()}")
    
    # All customers with scheduled follow-ups
    scheduled = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None)
    ).all()
    
    print(f"\n📊 Total customers with scheduled follow-ups: {len(scheduled)}")
    
    if scheduled:
        print("\n📋 Details of scheduled follow-ups:")
        print("-" * 70)
        for i, c in enumerate(scheduled[:10], 1):  # Show first 10
            time_diff_sec = (c.next_followup_time - now).total_seconds() if c.next_followup_time else None
            time_diff_min = int(time_diff_sec / 60) if time_diff_sec else None
            
            if time_diff_sec and time_diff_sec <= 0:
                status = "✅ DUE NOW"
            elif time_diff_sec:
                status = f"⏳ Due in {time_diff_min} minutes"
            else:
                status = "❓ Unknown"
            
            print(f"{i}. Customer: {c.wa_id}")
            print(f"   Name: {c.name or 'N/A'}")
            print(f"   Scheduled Time: {c.next_followup_time}")
            print(f"   Status: {status}")
            print(f"   Last Message Type: {c.last_message_type or 'N/A'}")
            print(f"   Last Interaction: {c.last_interaction_time or 'Never'}")
            print()
        
        # Count by status
        due_now = [c for c in scheduled if c.next_followup_time and c.next_followup_time <= now]
        future = [c for c in scheduled if c.next_followup_time and c.next_followup_time > now]
        
        print("\n📈 Summary:")
        print(f"   ✅ Due Now: {len(due_now)}")
        print(f"   ⏳ Future: {len(future)}")
        
        if due_now:
            print(f"\n⚠️  WARNING: {len(due_now)} customer(s) are due but scheduler isn't finding them!")
            print("   Possible causes:")
            print("   1. Scheduler not running")
            print("   2. Database timezone mismatch")
            print("   3. Query filter issue")
        
    else:
        print("\n❌ No customers have follow-ups scheduled!")
        print("\n💡 To test, send a message that triggers mr_welcome template")
        print("   Then check if follow-up gets scheduled")
    
    # Check recent customers
    print("\n" + "=" * 70)
    print("👥 Recent customers (last 5 created):")
    print("-" * 70)
    recent = db.query(Customer).order_by(Customer.created_at.desc()).limit(5).all()
    for c in recent:
        print(f"   {c.wa_id} - Created: {c.created_at}, Next Follow-up: {c.next_followup_time or 'None'}")
    
    db.close()
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ Debug complete!")

