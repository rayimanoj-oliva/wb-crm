# example in service.py
from uuid import UUID

from cache.redis_connection import get_redis_client


def increment_unread(wa_id: str):
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.incr(f"unread:{wa_id}")
        except Exception:
            pass


def reset_unread(wa_id: str):
    redis_client = get_redis_client()
    if redis_client:
        try:
            key = f"unread:{wa_id}"
            redis_client.set(key, 0)
        except Exception:
            pass

def get_unread(wa_id: str) -> int:
    redis_client = get_redis_client()
    if not redis_client:
        return 0
    try:
        key = f"unread:{wa_id}"
        return int(redis_client.get(key) or 0)
    except Exception:
        return 0
