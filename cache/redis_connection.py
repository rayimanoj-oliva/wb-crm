# redis_connection.py
import redis

redis_client = redis.StrictRedis(
    host="localhost",  # or your Redis server IP
    port=6379,
    db=0,
    decode_responses=True  # To return string instead of bytes
)
