from datetime import datetime, timedelta
from typing import Optional, Tuple
import uuid
import logging
import sys

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from models.models import Customer

import os
import requests
from fastapi import HTTPException
from services import whatsapp_service, customer_service, message_service
from schemas.message_schema import MessageCreate
from schemas.customer_schema import CustomerCreate
from config.constants import get_messages_url
from cache.redis_connection import get_redis_client
from marketing.whatsapp_numbers import get_number_config, TREATMENT_FLOW_ALLOWED_PHONE_IDS, WHATSAPP_NUMBERS
from utils.flow_log import log_flow_event  # flow logs
import json

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


# Helper: check if a WA user is currently in lead appointment flow (skip followups in that case)
# Helper: check if a WA user is currently in lead appointment flow (skip followups in that case)
def _is_in_lead_appointment_flow(wa_id: Optional[str]) -> bool:
    try:
        if not wa_id:
            return False
        # Import here to avoid heavy module imports at top-level
        from controllers.web_socket import lead_appointment_state  # type: ignore
        state = lead_appointment_state.get(wa_id) or {}
        # Only treat as in lead flow if explicit context is set
        return bool(state) and (state.get("flow_context") == "lead_appointment")
    except Exception:
        return False


# Resolve credentials to always use the Treatment Flow number when available
def _resolve_marketing_credentials(db: Session, *, wa_id: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Resolve credentials strictly for Treatment Flow numbers, independent per number.
    Returns (access_token, phone_id, display_from_digits).
    Preference order:
      1) phone_id stored in controllers.web_socket.appointment_state[wa_id]["treatment_flow_phone_id"]
      2) Env TREATMENT_FLOW_PHONE_ID/WELCOME_PHONE_ID if they are in allowed set
      3) First allowed phone id from mapping
    """
    phone_id_pref: Optional[str] = None
    display_from = os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")

    # 1) Stored phone id from state
    if wa_id:
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            stored_pid = st.get("treatment_flow_phone_id")
            if stored_pid and str(stored_pid) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                phone_id_pref = str(stored_pid)
                logger.debug(f"[_resolve_marketing_credentials] Using stored phone_id {phone_id_pref} for wa_id={wa_id}")
        except Exception as e:
            logger.debug(f"[_resolve_marketing_credentials] No stored phone_id for {wa_id}: {e}")

    # 2) Env-configured if allowed
    if not phone_id_pref:
        pid_env = os.getenv("TREATMENT_FLOW_PHONE_ID") or os.getenv("WELCOME_PHONE_ID") or os.getenv("WHATSAPP_PHONE_ID")
        if pid_env and str(pid_env) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
            phone_id_pref = str(pid_env)
            logger.debug(f"[_resolve_marketing_credentials] Using env phone_id {phone_id_pref}")

    # 3) Fallback to first allowed id in mapping
    if not phone_id_pref:
        try:
            phone_id_pref = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
            logger.debug(f"[_resolve_marketing_credentials] Fallback to first allowed phone_id {phone_id_pref}")
        except Exception:
            pass

    # Resolve token + display_from from mapping
    token: Optional[str] = None
    if phone_id_pref:
        try:
            cfg = get_number_config(str(phone_id_pref))
            if cfg and cfg.get("token"):
                token = cfg.get("token")
                try:
                    import re as _re
                    display_from = _re.sub(r"\D", "", (cfg.get("name") or "")) or display_from
                except Exception:
                    pass
        except Exception:
            pass

    # Final fallback: DB token but still force an allowed phone_id
    if not token:
        tok = whatsapp_service.get_latest_token(db)
        if not tok:
            raise HTTPException(status_code=400, detail="Token not available")
        token = tok.token
        if not phone_id_pref:
            # last resort - pick any allowed or default to known id
            phone_id_pref = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0] if TREATMENT_FLOW_ALLOWED_PHONE_IDS else os.getenv("WHATSAPP_PHONE_ID", "859830643878412")

    return token, str(phone_id_pref), display_from

# Follow-up timing constants (in minutes)
FOLLOW_UP_1_DELAY_MINUTES = 5  # Time before sending Follow-Up 1
FOLLOW_UP_2_DELAY_MINUTES = 30  # Time after Follow-Up 1 before sending Follow-Up 2

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


def schedule_next_followup(db: Session, *, customer_id, delay_minutes: int = FOLLOW_UP_1_DELAY_MINUTES, stage_label: Optional[str] = None) -> None:
    customer: Optional[Customer] = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.warning(f"Customer {customer_id} not found for scheduling follow-up")
        return
    # Skip scheduling follow-ups while user is in lead appointment flow
    if _is_in_lead_appointment_flow(getattr(customer, "wa_id", None)):
        logger.info(f"[followup_service] Skipping follow-up scheduling for {customer.wa_id} - user in lead appointment flow")
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


def mark_customer_replied(db: Session, *, customer_id, reset_followup_timer: bool = True) -> None:
    """
    Mark customer as replied and optionally reset the follow-up timer.
    
    Args:
        customer_id: The customer ID
        reset_followup_timer: If True, schedule a new follow-up timer starting from now (default: True)
                             This ensures the follow-up countdown restarts from the customer's last interaction
    """
    customer: Optional[Customer] = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        logger.warning(f"[followup_service] mark_customer_replied: Customer {customer_id} not found")
        return
    
    had_followup = customer.next_followup_time is not None
    followup_time = customer.next_followup_time
    
    customer.last_interaction_time = datetime.utcnow()
    # Clear any pending follow-up since customer replied
    customer.next_followup_time = None
    customer.last_message_type = None
    
    # Reset follow-up timer unless user is in lead appointment flow
    if reset_followup_timer and not _is_in_lead_appointment_flow(getattr(customer, "wa_id", None)):
        followup_time = datetime.utcnow() + timedelta(minutes=FOLLOW_UP_1_DELAY_MINUTES)
        customer.next_followup_time = followup_time
        logger.info(f"[followup_service] Reset follow-up timer for customer {customer.wa_id} (ID: {customer_id}) - new Follow-Up 1 scheduled at {followup_time} (from last interaction, {FOLLOW_UP_1_DELAY_MINUTES} minutes)")
    elif reset_followup_timer:
        logger.info(f"[followup_service] Not scheduling follow-up for {customer.wa_id} - user in lead appointment flow")
    
    db.add(customer)
    try:
        db.commit()
        if had_followup and not reset_followup_timer:
            logger.info(f"[followup_service] Cleared follow-up for customer {customer.wa_id} (ID: {customer_id}) - had scheduled follow-up at {followup_time}")
        elif not had_followup and not reset_followup_timer:
            logger.debug(f"[followup_service] mark_customer_replied for customer {customer.wa_id} (ID: {customer_id}) - no follow-up was scheduled")
    except Exception as e:
        logger.error(f"[followup_service] Failed to mark customer replied: {e}")
        db.rollback()


def due_customers_for_followup(db: Session):
    now = datetime.utcnow()
    
    # Query for due customers - only those where follow-up time has passed
    # AND user hasn't interacted since the follow-up was scheduled
    due = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None),
        Customer.next_followup_time <= now
    ).all()
    
    # Filter out customers who have interacted recently
    # Follow-Up 1 should ONLY be sent if 2 minutes have passed since last user interaction
    actually_due = []
    for c in due:
        # Skip users currently in lead appointment flow
        if _is_in_lead_appointment_flow(getattr(c, "wa_id", None)):
            logger.info(f"[followup_service] Skipping due follow-up for {c.wa_id} - user in lead appointment flow")
            c.next_followup_time = None
            db.add(c)
            continue
        if c.last_interaction_time is None:
            # No interaction recorded, proceed with follow-up (shouldn't happen normally)
            actually_due.append(c)
            continue
        
        # Calculate time since last user interaction
        time_since_last_interaction = (now - c.last_interaction_time).total_seconds() / 60
        
        # Only send follow-up if at least 2 minutes have passed since last interaction
        if time_since_last_interaction >= FOLLOW_UP_1_DELAY_MINUTES:
            # User hasn't interacted in the last 2 minutes, so follow-up is valid
            actually_due.append(c)
        else:
            # User interacted less than 2 minutes ago - clear this stale follow-up
            logger.info(f"[followup_service] Skipping follow-up for customer {c.wa_id} - user interacted {time_since_last_interaction:.2f} minutes ago (less than {FOLLOW_UP_1_DELAY_MINUTES} min threshold)")
            c.next_followup_time = None
            db.add(c)
    
    # Commit any cleared follow-ups
    if len(actually_due) < len(due):
        try:
            db.commit()
            logger.info(f"[followup_service] Cleared {len(due) - len(actually_due)} stale follow-up(s) - users interacted recently")
        except Exception as e:
            logger.error(f"[followup_service] Failed to clear stale follow-ups: {e}")
            db.rollback()
    
    due = actually_due
    
    # Enhanced debugging: always show status with detailed query info
    total_scheduled = db.query(Customer).filter(Customer.next_followup_time.isnot(None)).count()
    
    # Also get customers that should be due (for debugging)
    if total_scheduled > 0:
        all_scheduled = db.query(Customer).filter(
            Customer.next_followup_time.isnot(None)
        ).all()
        
        # Check for any customers that should be due but weren't found
        past_due = [c for c in all_scheduled if c.next_followup_time and c.next_followup_time <= now]
        
        if len(past_due) != len(due):
            logger.warning(f"[followup_service] QUERY MISMATCH! Found {len(past_due)} customers that should be due, but query returned {len(due)}")
            for c in past_due:
                if c not in due:
                    logger.warning(f"[followup_service] Customer {c.wa_id} (ID: {c.id}) has next_followup_time={c.next_followup_time} (past due) but not in query results!")
    
    if total_scheduled == 0:
        logger.info(f"[followup_service] Current UTC time: {now} - No customers have follow-ups scheduled")
        sys.stdout.flush()
    elif not due:
        # Get a few examples of scheduled follow-ups
        examples = db.query(Customer).filter(
            Customer.next_followup_time.isnot(None)
        ).order_by(Customer.next_followup_time).limit(5).all()
        
        logger.info(f"[followup_service] Current UTC time: {now}")
        logger.info(f"[followup_service] Found {total_scheduled} customer(s) with follow-ups scheduled, but none are due yet")
        
        for ex in examples:
            if ex.next_followup_time:
                time_diff = (ex.next_followup_time - now).total_seconds()
                minutes_diff = int(time_diff / 60)
                status = "PAST (due)" if time_diff <= 0 else f"FUTURE ({minutes_diff} min away)"
                logger.info(f"[followup_service] Example: Customer {ex.wa_id} (ID: {ex.id}) - next_followup_time: {ex.next_followup_time}, status: {status}, time_diff: {time_diff:.1f} seconds")
        sys.stdout.flush()
    else:
        logger.info(f"[followup_service] Current UTC time: {now} - Found {len(due)} customer(s) due for follow-up out of {total_scheduled} scheduled")
        for d in due:
            logger.info(f"[followup_service] Due customer: {d.wa_id} (ID: {d.id}), next_followup_time: {d.next_followup_time}, last_message_type: {d.last_message_type}")
        sys.stdout.flush()
    
    return due


async def send_followup1_interactive(db: Session, *, wa_id: str, from_wa_id: str = None):
    """Send Follow-Up 1 as an interactive Yes/No message.
    This function is self-contained and does not rely on other send helpers.
    """
    # Guard: do not send follow-ups for users in lead appointment flow
    if _is_in_lead_appointment_flow(wa_id):
        logger.info(f"[followup_service] Not sending Follow-Up 1 to {wa_id} - user in lead appointment flow")
        return
    logger.info(f"Starting Follow-Up 1 send to {wa_id}")
    
    # Resolve credentials for Treatment Flow number (independent per wa_id)
    access_token, phone_id, display_from = _resolve_marketing_credentials(db, wa_id=wa_id)

    # Restrict strictly to allowed numbers
    if str(phone_id) not in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
        logger.info(f"[followup_service] Blocked Follow-Up 1 for {wa_id} - phone_id {phone_id} not allowed")
        return

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

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
        from_wa_id=(from_wa_id or display_from),
        to_wa_id=wa_id,
        type="interactive",
        body="Follow-Up 1 (Yes/No)",
        timestamp=datetime.utcnow(),
        customer_id=customer.id,
    )
    message_service.create_message(db, message_data)
    logger.debug(f"Follow-Up 1 message persisted to database for customer_id: {customer.id}, wa_id: {wa_id}")

    # Flow log: Follow-Up 1 dispatched (pending)
    try:
        cust_name = getattr(customer, "name", None) or ""
        log_flow_event(
            db,
            flow_type="treatment",
            step="follow_up_1_sent",
            status_code=200,
            wa_id=wa_id,
            name=cust_name,
            description="Follow-Up 1 interactive sent",
        )
    except Exception:
        pass
    
    try:
        # Also mark Follow-Up 1 state on the customer and schedule Follow-Up 2 timer
        cust = db.query(Customer).filter(Customer.id == customer.id).first()
        if cust:
            cust.last_message_type = "follow_up_1_sent"
            cust.next_followup_time = datetime.utcnow() + timedelta(minutes=FOLLOW_UP_2_DELAY_MINUTES)
            db.add(cust)
        db.commit()
        logger.info(f"Follow-Up 1 completed for {wa_id}. Scheduled Follow-Up 2 in {FOLLOW_UP_2_DELAY_MINUTES} minutes")
    except Exception as e:
        logger.error(f"Failed to update customer state after Follow-Up 1 to {wa_id}: {e}")
        db.rollback()


async def send_followup2(db: Session, *, wa_id: str, from_wa_id: str = None):
    """Send Follow-Up 2 message to customer.
    This function sends the Follow-Up 2 text message and logs the process.
    """
    # Guard: do not send follow-ups for users in lead appointment flow
    if _is_in_lead_appointment_flow(wa_id):
        logger.info(f"[followup_service] Not sending Follow-Up 2 to {wa_id} - user in lead appointment flow")
        return
    logger.info(f"Starting Follow-Up 2 send to {wa_id}")
    
    # Resolve credentials for Treatment Flow number (independent per wa_id)
    access_token, phone_id, display_from = _resolve_marketing_credentials(db, wa_id=wa_id)

    # Restrict strictly to allowed numbers
    if str(phone_id) not in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
        logger.info(f"[followup_service] Blocked Follow-Up 2 for {wa_id} - phone_id {phone_id} not allowed")
        return

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": FOLLOW_UP_2_TEXT}
    }

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
        from_wa_id=(from_wa_id or display_from),
        to_wa_id=wa_id,
        type="text",
        body=FOLLOW_UP_2_TEXT,
        timestamp=datetime.utcnow(),
        customer_id=customer.id,
    )
    message_service.create_message(db, message_data)
    logger.debug(f"Follow-Up 2 message persisted to database for customer_id: {customer.id}, wa_id: {wa_id}")

    # Flow log: Follow-Up 2 dispatched
    try:
        cust_name = getattr(customer, "name", None) or ""
        log_flow_event(
            db,
            flow_type="treatment",
            step="follow_up_2_sent",
            status_code=200,
            wa_id=wa_id,
            name=cust_name,
            description="Follow-Up 2 text sent",
        )
    except Exception:
        pass
    
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

    # After Follow-Up 2: if user still hasn't replied, push a lead only if none exists
    try:
        from models.models import Lead as _Lead

        # Normalize wa_id to phone (digits only) and last 10 digits variant
        def _digits_only(s: Optional[str]) -> str:
            try:
                import re as _re
                return _re.sub(r"\D", "", s or "")
            except Exception:
                return s or ""

        phone_digits = _digits_only(wa_id)
        last10 = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits

        # Re-fetch customer to get possible customer_id linkage
        cust_for_link = db.query(Customer).filter(Customer.id == customer.id).first() if customer else None
        cust_id = getattr(cust_for_link, "id", None)

        # Robust duplicate check (within last 24 hours):
        # - Same wa_id
        # - Same phone exact (digits only stored) OR phone ends with last 10
        # - Same customer_id linkage if present
        window_start = datetime.utcnow() - timedelta(hours=24)
        existing = (
            db.query(_Lead)
            .filter(
                or_(
                    _Lead.wa_id == wa_id,
                    _Lead.phone == phone_digits,
                    func.right(_Lead.phone, 10) == last10,
                    (_Lead.customer_id == cust_id) if cust_id else False,
                )
            )
            .filter(_Lead.created_at >= window_start)
            .order_by(_Lead.created_at.desc())
            .first()
        )

        if not existing:
            # Double-check in Zoho by phone to avoid duplicates even if local DB missed a record
            try:
                from controllers.components.lead_appointment_flow.zoho_lead_service import zoho_lead_service  # type: ignore
                zoho_hit = zoho_lead_service.find_existing_lead_by_phone(phone_digits or wa_id)
            except Exception as e:
                logger.warning(f"[followup_service] Zoho duplicate check failed for {wa_id}: {e}")
                zoho_hit = None

            if zoho_hit:
                lead_id_existing = str((zoho_hit or {}).get("id") or (zoho_hit or {}).get("Id") or "")
                logger.info(f"[followup_service] Zoho lead already exists for {wa_id} (lead_id={lead_id_existing}). Skipping dropoff lead creation.")
                # Optional: log informational result
                try:
                    log_flow_event(
                        db,
                        flow_type="lead_appointment",
                        step="result",
                        status_code=200,
                        wa_id=wa_id,
                        name=getattr(customer, "name", None) or "",
                        description=f"Duplicate avoided after Follow-Up 2: existing Zoho lead {lead_id_existing}",
                    )
                except Exception:
                    pass
                return message_id

            logger.info(f"[followup_service] No existing lead for {wa_id} (DB+Zoho). Creating dropoff lead after Follow-Up 2.")
            try:
                from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_dropoff  # type: ignore
                res = await create_lead_for_dropoff(db, wa_id=wa_id, customer=customer, dropoff_point="no_response_followup2")
                # Log flow
                try:
                    log_flow_event(
                        db,
                        flow_type="lead_appointment",
                        step="result",
                        status_code=200 if (res or {}).get("success") else 500,
                        wa_id=wa_id,
                        name=getattr(customer, "name", None) or "",
                        description="Lead created after Follow-Up 2 (no response)" if (res or {}).get("success") else f"Lead creation failed after Follow-Up 2: {(res or {}).get('error')}",
                        response_json=json.dumps(res, default=str) if res is not None else None,
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"[followup_service] Dropoff lead creation failed for {wa_id}: {e}")
        else:
            logger.info(f"[followup_service] Existing lead found for {wa_id} (lead_id={existing.zoho_lead_id}). Skipping dropoff lead creation.")
    except Exception as e:
        logger.error(f"[followup_service] Post-FU2 lead check failed for {wa_id}: {e}")

    return message_id

