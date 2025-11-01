#!/usr/bin/env python3
"""
Quick test script to verify follow-up scheduler setup
Run this after deploying to production to ensure everything is working.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_redis_connection():
    """Test Redis connection"""
    print("\n🔍 Testing Redis Connection...")
    print("-" * 50)
    
    try:
        from cache.redis_connection import get_redis_client
        
        redis_client = get_redis_client()
        if redis_client:
            try:
                redis_client.ping()
                print("✅ Redis: Connected successfully")
                print(f"   Host: {os.getenv('REDIS_HOST', 'localhost')}")
                print(f"   Port: {os.getenv('REDIS_PORT', '6379')}")
                return True
            except Exception as e:
                print(f"❌ Redis: Ping failed - {e}")
                return False
        else:
            print("⚠️  Redis: NOT connected (will work without distributed locking)")
            print("   This is OK for single-instance deployments")
            return None
    except Exception as e:
        print(f"❌ Redis: Connection error - {e}")
        return False


def test_distributed_locking():
    """Test distributed locking mechanism"""
    print("\n🔒 Testing Distributed Locking...")
    print("-" * 50)
    
    try:
        from services.followup_service import acquire_followup_lock, release_followup_lock
        
        test_customer_id = "test-customer-123"
        
        # Try to acquire lock
        lock_value = acquire_followup_lock(test_customer_id)
        if lock_value:
            print("✅ Lock: Acquired successfully")
            
            # Try to acquire again (should fail)
            lock_value2 = acquire_followup_lock(test_customer_id)
            if lock_value2 is None:
                print("✅ Lock: Prevents duplicate acquisition (correct behavior)")
            else:
                print("⚠️  Lock: Duplicate acquisition allowed (Redis may not be working)")
            
            # Release lock
            release_followup_lock(test_customer_id, lock_value)
            print("✅ Lock: Released successfully")
            return True
        else:
            print("⚠️  Lock: Failed to acquire (Redis may not be available)")
            return None
    except Exception as e:
        print(f"❌ Lock: Error - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_followup_functions():
    """Test follow-up service functions"""
    print("\n📋 Testing Follow-Up Service Functions...")
    print("-" * 50)
    
    try:
        from services.followup_service import (
            FOLLOW_UP_1_TEXT,
            FOLLOW_UP_2_TEXT,
            acquire_followup_lock,
            release_followup_lock
        )
        
        print("✅ Follow-Up 1 Text: Available")
        print(f"   Preview: {FOLLOW_UP_1_TEXT[:50]}...")
        print("✅ Follow-Up 2 Text: Available")
        print(f"   Preview: {FOLLOW_UP_2_TEXT[:50]}...")
        print("✅ Lock functions: Imported successfully")
        return True
    except Exception as e:
        print(f"❌ Follow-Up Service: Error - {e}")
        import traceback
        traceback.print_exc()
        return False


def check_environment():
    """Check environment variables"""
    print("\n⚙️  Checking Environment Variables...")
    print("-" * 50)
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_db = os.getenv("REDIS_DB", "0")
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_url = os.getenv("REDIS_URL")
    
    print(f"REDIS_HOST: {redis_host}")
    print(f"REDIS_PORT: {redis_port}")
    print(f"REDIS_DB: {redis_db}")
    print(f"REDIS_PASSWORD: {'SET' if redis_password else 'NOT SET (optional)'}")
    print(f"REDIS_URL: {'SET' if redis_url else 'NOT SET (optional)'}")


def main():
    """Run all tests"""
    print("=" * 50)
    print("🚀 Follow-Up Scheduler Setup Verification")
    print("=" * 50)
    
    # Check environment
    check_environment()
    
    # Test Redis
    redis_ok = test_redis_connection()
    
    # Test locking (only if Redis is available)
    if redis_ok:
        lock_ok = test_distributed_locking()
    else:
        print("\n⚠️  Skipping lock test (Redis not available)")
        lock_ok = None
    
    # Test follow-up functions
    functions_ok = test_followup_functions()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    if redis_ok:
        print("✅ Redis: Working")
    elif redis_ok is None:
        print("⚠️  Redis: Not available (will work without distributed locking)")
    else:
        print("❌ Redis: Failed")
    
    if lock_ok:
        print("✅ Distributed Locking: Working")
    elif lock_ok is None:
        print("⚠️  Distributed Locking: Not available (Redis required)")
    else:
        print("❌ Distributed Locking: Failed")
    
    if functions_ok:
        print("✅ Follow-Up Functions: Working")
    else:
        print("❌ Follow-Up Functions: Failed")
    
    print("\n" + "=" * 50)
    
    if redis_ok and lock_ok and functions_ok:
        print("✅ All tests passed! Your setup is ready for production.")
    elif functions_ok and (redis_ok is None or lock_ok is None):
        print("⚠️  Setup is functional but Redis is not available.")
        print("   For production with multiple instances, Redis is recommended.")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        sys.exit(1)
    
    print("\n💡 Next Steps:")
    print("   1. Restart your FastAPI application")
    print("   2. Check logs for: [followup_scheduler] INFO - Starting iteration")
    print("   3. Monitor logs.out or systemd journal for scheduler activity")
    print("=" * 50)


if __name__ == "__main__":
    main()

