# redis_connection.py
import os
import redis
from typing import Optional

# Get Redis configuration from environment variables with fallback
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Optional: Redis URL (if provided, will override host/port/db)
REDIS_URL = os.getenv("REDIS_URL", None)

redis_client: Optional[redis.StrictRedis] = None

def get_redis_client() -> Optional[redis.StrictRedis]:
    """Get Redis client with proper error handling. Returns None if Redis is not available."""
    global redis_client
    if redis_client is not None:
        return redis_client
    
    try:
        if REDIS_URL:
            redis_client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
        else:
            redis_client = redis.StrictRedis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
        # Test connection
        redis_client.ping()
        print(f"[Redis] Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return redis_client
    except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
        print(f"[Redis] WARNING - Could not connect to Redis: {e}. Running without distributed locking.")
        redis_client = None
        return None

# Initialize on import
redis_client = get_redis_client()
