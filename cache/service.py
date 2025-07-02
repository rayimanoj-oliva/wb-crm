# example in service.py
from uuid import UUID

from cache.redis_connection import redis_client


def increment_unread(wa_id: str):
    redis_client.incr(f"unread:{wa_id}")


def reset_unread(wa_id: str):
    key = f"unread:{wa_id}"
    redis_client.set(key, 0)

def get_unread(wa_id: str) -> int:
    key = f"unread:{wa_id}"
    return int(redis_client.get(key) or 0)
