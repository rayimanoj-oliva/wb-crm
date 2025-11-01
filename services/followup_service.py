from datetime import datetime, timedelta
from typing import Optional
import uuid
import logging
import sys

from sqlalchemy.orm import Session

from models.models import Customer

import os
import requests
from fastapi import HTTPException
from services import whatsapp_service, customer_service, message_service
from schemas.message_schema import MessageCreate
from schemas.customer_schema import CustomerCreate
from config.constants import get_messages_url
from cache.redis_connection import get_redis_client

# Create logger for this module
logger = logging.getLogger("followup_service")
# Ensure logger level is set to DEBUG and it propagates to root logger
logger.setLevel(logging.DEBUG)
# Ensure handler is added if not already present (for cases where logging isn't configured yet)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = True  # Ensure messages propagate to root logger


FOLLOW_UP_1_TEXT = (
    "👋 Hi! Just checking in — are we still connected?\n\n"
    "Reply to continue. 💬\n\n"
    
)
FOLLOW_UP_2_TEXT = (
    "Hi again! 😊 Since we haven't heard from you, our team will give you a quick call to assist you.\n\n"
    "Thank you for choosing Oliva Clinics!"
)


def acquire_followup_lock(customer_id: str, lock_ttl: int = 300) -> Optional[str]:
    """
    Acquire a distributed lock for processing a customer's follow-up.
    Returns lock_key if acquired, None if already locked or Redis unavailable.
    
    Args:
        customer_id: The customer ID to lock
        lock_ttl: Lock time-to-live in seconds (default 5 minutes)
    
    Returns:
        lock_key if lock acquired, None otherwise
    """
    redis_client = get_redis_client()
    if not redis_client:
        # Redis not available - return a fake lock key to allow processing
        # In production, you might want to fail here or use DB-based locking
        logger.warning(f"Redis unavailable, processing without distributed lock for customer {customer_id}")
        return f"lock:{customer_id}:{uuid.uuid4()}"
    
    lock_key = f"followup_lock:{customer_id}"
    lock_value = str(uuid.uuid4())
    
    try:
        # Try to acquire lock (SET with NX - only set if not exists)
        acquired = redis_client.set(lock_key, lock_value, nx=True, ex=lock_ttl)
        if acquired:
            return lock_value
        else:
            logger.info(f"Customer {customer_id} already being processed by another instance")
            return None
    except Exception as e:
        logger.error(f"Failed to acquire lock for customer {customer_id}: {e}")
        return None


def release_followup_lock(customer_id: str, lock_value: str) -> None:
    """
    Release a distributed lock for a customer's follow-up.
    
    Args:
        customer_id: The customer ID
        lock_value: The lock value returned by acquire_followup_lock
    """
    redis_client = get_redis_client()
    if not redis_client:
        return
    
    lock_key = f"followup_lock:{customer_id}"
    
    try:
        # Use Lua script to ensure we only delete if the value matches
        # This prevents deleting a lock acquired by another instance
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        redis_client.eval(lua_script, 1, lock_key, lock_value)
    except Exception as e:
        logger.error(f"Failed to release lock for customer {customer_id}: {e}")


def schedule_next_followup(db: Session, *, customer_id, delay_minutes: int = 2, stage_label: Optional[str] = None) -> None:
    customer: Optional[Customer] = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.warning(f"Customer {customer_id} not found for scheduling follow-up")
        return
    # If a Follow-Up 1 wait window is already active, do not overwrite it with generic outbound scheduling
    if stage_label is None and (customer.last_message_type or "").lower() == "follow_up_1_sent" and customer.next_followup_time:
        logger.info(f"Skipping follow-up scheduling for customer {customer_id} - Follow-Up 1 already active")
        return
    followup_time = datetime.utcnow() + timedelta(minutes=delay_minutes)
    customer.next_followup_time = followup_time
    if stage_label:
        customer.last_message_type = stage_label
    db.add(customer)
    try:
        db.commit()
        logger.info(f"Scheduled follow-up for customer {customer_id} (wa_id: {customer.wa_id}) at {followup_time}, stage_label: {stage_label}")
    except Exception as e:
        logger.error(f"Failed to commit follow-up schedule for customer {customer_id}: {e}")
        db.rollback()


def mark_customer_replied(db: Session, *, customer_id) -> None:
    customer: Optional[Customer] = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        return
    customer.last_interaction_time = datetime.utcnow()
    # Clear any pending follow-up since customer replied
    customer.next_followup_time = None
    customer.last_message_type = None
    db.add(customer)
    try:
        db.commit()
    except Exception:
        db.rollback()


def due_customers_for_followup(db: Session):
    now = datetime.utcnow()
    due = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None),
        Customer.next_followup_time <= now
    ).all()
    
    # Enhanced debugging: always show status
    # Use INFO level to ensure messages appear even if DEBUG is filtered by uvicorn
    total_scheduled = db.query(Customer).filter(Customer.next_followup_time.isnot(None)).count()
    
    if total_scheduled == 0:
        logger.info(f"[followup_service] Current UTC time: {now} - No customers have follow-ups scheduled")
        sys.stdout.flush()  # Explicitly flush to ensure immediate output
    elif not due:
        # Get a few examples of scheduled follow-ups
        examples = db.query(Customer).filter(
            Customer.next_followup_time.isnot(None)
        ).limit(3).all()
        logger.info(f"[followup_service] Current UTC time: {now}")
        logger.info(f"[followup_service] Found {total_scheduled} customer(s) with follow-ups scheduled, but none are due yet")
        for ex in examples:
            time_diff = (ex.next_followup_time - now).total_seconds() if ex.next_followup_time else None
            status = "PAST (due)" if time_diff and time_diff <= 0 else f"FUTURE ({int(time_diff/60)} min away)" if time_diff else "NULL"
            logger.info(f"[followup_service] Example: Customer {ex.wa_id} - next_followup_time: {ex.next_followup_time}, status: {status}")
        sys.stdout.flush()  # Explicitly flush to ensure immediate output
    else:
        logger.info(f"[followup_service] Current UTC time: {now} - Found {len(due)} customer(s) due for follow-up out of {total_scheduled} scheduled")
        sys.stdout.flush()  # Explicitly flush to ensure immediate output
    
    return due


async def send_followup1_interactive(db: Session, *, wa_id: str, from_wa_id: str = "917729992376"):
    """Send Follow-Up 1 as an interactive Yes/No message.
    This function is self-contained and does not rely on other send helpers.
    """
    logger.info(f"Starting Follow-Up 1 send to {wa_id}")
    
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        logger.error(f"Token not available for Follow-Up 1 to {wa_id}")
        raise HTTPException(status_code=400, detail="Token not available")

    headers = {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }

    # Compose an interactive button message with Yes/No
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": FOLLOW_UP_1_TEXT},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "followup_yes", "title": "✅ Yes"}},
                    
                ]
            }
        }
    }

    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    logger.debug(f"Sending Follow-Up 1 interactive message to {wa_id} via phone_id {phone_id}")
    
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        logger.error(f"Failed to send Follow-Up 1 interactive to {wa_id}: Status {res.status_code}, Response: {res.text}")
        raise HTTPException(status_code=500, detail=f"Failed to send follow-up 1 interactive: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    logger.debug(f"Follow-Up 1 sent successfully to {wa_id}, Message ID: {message_id}")
    
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    # Persist an entry for the interactive message send
    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="interactive",
        body="Follow-Up 1 (Yes/No)",
        timestamp=datetime.utcnow(),
        customer_id=customer.id,
    )
    message_service.create_message(db, message_data)
    logger.debug(f"Follow-Up 1 message persisted to database for customer_id: {customer.id}, wa_id: {wa_id}")
    
    try:
        # Also mark Follow-Up 1 state on the customer and schedule Follow-Up 2 timer (5 minutes)
        cust = db.query(Customer).filter(Customer.id == customer.id).first()
        if cust:
            cust.last_message_type = "follow_up_1_sent"
            cust.next_followup_time = datetime.utcnow() + timedelta(minutes=5)
            db.add(cust)
        db.commit()
        logger.info(f"Follow-Up 1 completed for {wa_id}. Scheduled Follow-Up 2 in 5 minutes")
    except Exception as e:
        logger.error(f"Failed to update customer state after Follow-Up 1 to {wa_id}: {e}")
        db.rollback()


async def send_followup2(db: Session, *, wa_id: str, from_wa_id: str = "917729992376"):
    """Send Follow-Up 2 message to customer.
    This function sends the Follow-Up 2 text message and logs the process.
    """
    logger.info(f"Starting Follow-Up 2 send to {wa_id}")
    
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        logger.error(f"Token not available for Follow-Up 2 to {wa_id}")
        raise HTTPException(status_code=400, detail="Token not available")

    headers = {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": FOLLOW_UP_2_TEXT}
    }

    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    logger.debug(f"Sending Follow-Up 2 message to {wa_id} via phone_id {phone_id}")
    
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        logger.error(f"Failed to send Follow-Up 2 to {wa_id}: Status {res.status_code}, Response: {res.text}")
        raise HTTPException(status_code=500, detail=f"Failed to send follow-up 2: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    logger.debug(f"Follow-Up 2 sent successfully to {wa_id}, Message ID: {message_id}")
    
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    # Persist an entry for the Follow-Up 2 message send
    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="text",
        body=FOLLOW_UP_2_TEXT,
        timestamp=datetime.utcnow(),
        customer_id=customer.id,
    )
    message_service.create_message(db, message_data)
    logger.debug(f"Follow-Up 2 message persisted to database for customer_id: {customer.id}, wa_id: {wa_id}")
    
    try:
        # Mark Follow-Up 2 state on the customer
        cust = db.query(Customer).filter(Customer.id == customer.id).first()
        if cust:
            cust.last_message_type = "follow_up_2_sent"
            cust.next_followup_time = None
            db.add(cust)
        db.commit()
        logger.info(f"Follow-Up 2 completed for {wa_id}. Follow-up sequence finished")
    except Exception as e:
        logger.error(f"Failed to update customer state after Follow-Up 2 to {wa_id}: {e}")
        db.rollback()
    
    return message_id

