"""
Campaign Message Consumer

Processes messages from RabbitMQ queue and sends WhatsApp messages.

FIXES APPLIED:
- Proper DB session management (no leaks)
- Rate limiting for WhatsApp API
- Token refresh handling
- Detailed logging to CampaignLog table
- Proper error handling with logging
- Consolidated UUID imports
"""

import time
import json
import logging
from datetime import datetime
from uuid import UUID
from contextlib import contextmanager

import requests
import pika
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import SessionLocal
from models.models import (
    JobStatus, Campaign, Job, Customer, CampaignRecipient, CampaignLog, WhatsAppAPILog, Message
)
from services import whatsapp_service
from services import message_service
from services import customer_service
from schemas.message_schema import MessageCreate
from schemas.customer_schema import CustomerCreate
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Rate Limiting Configuration - Meta WhatsApp API Limits
# =============================================================================
# Meta allows MAX 80 messages/second for WhatsApp Business API
# Formula: RATE_LIMIT_DELAY_MS = 1000 / (80 / NUM_WORKERS)
#
# Examples:
#   - 1 worker:  1000 / 80 = 12.5ms  -> use 15ms (safe margin)
#   - 2 workers: 1000 / 40 = 25ms
#   - 4 workers: 1000 / 20 = 50ms
#   - 8 workers: 1000 / 10 = 100ms
# =============================================================================
META_MAX_MSG_PER_SECOND = 80
DEFAULT_NUM_WORKERS = 4  # Adjust based on how many workers you run

# Calculate delay per worker to stay within Meta's limit
RATE_LIMIT_DELAY_MS = max(15, int(1000 / (META_MAX_MSG_PER_SECOND / DEFAULT_NUM_WORKERS)))  # 50ms for 4 workers

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2  # Faster retries

# Worker configuration for high volume
PREFETCH_COUNT = 5  # Reduced to prevent overwhelming the API
HTTP_TIMEOUT = 15  # Reduced timeout for faster failure detection

# Token cache with expiry tracking
_token_cache = {
    "token": None,
    "fetched_at": None,
    "expires_in_seconds": 3600  # Assume 1 hour expiry
}

# HTTP Session with connection pooling for high throughput
_http_session = None

def get_http_session():
    """Get or create HTTP session with connection pooling"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        # Configure connection pooling for high volume
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,  # Number of connection pools
            pool_maxsize=50,      # Connections per pool
            max_retries=0         # We handle retries ourselves
        )
        _http_session.mount('https://', adapter)
        _http_session.mount('http://', adapter)
    return _http_session


@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    FIXES: Ensures session is always closed, even on exceptions.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


def get_token_with_refresh(db: Session) -> str:
    """
    Get WhatsApp token with automatic refresh if expired.
    FIXES: Token refresh handling.
    """
    global _token_cache

    now = datetime.utcnow()

    # Check if cached token is still valid
    if _token_cache["token"] and _token_cache["fetched_at"]:
        elapsed = (now - _token_cache["fetched_at"]).total_seconds()
        if elapsed < _token_cache["expires_in_seconds"] - 300:  # 5 min buffer
            return _token_cache["token"]

    # Fetch fresh token
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise Exception("No WhatsApp token available in database")

    _token_cache["token"] = token_obj.token
    _token_cache["fetched_at"] = now
    logger.info("WhatsApp token refreshed")

    return token_obj.token


def parse_uuid(value: str) -> UUID:
    """Safely parse string to UUID"""
    if isinstance(value, UUID):
        return value
    return UUID(value)


def upsert_campaign_log(
    db: Session,
    campaign_id: UUID,
    job_id: UUID,
    target_type: str,
    target_id: UUID,
    phone_number: str,
    status: str,
    error_code: str = None,
    error_message: str = None,
    http_status_code: int = None,
    whatsapp_message_id: str = None,
    request_payload: dict = None,
    response_data: dict = None,
    processing_time_ms: int = None
):
    """
    Create or update a log entry in campaign_logs table.

    UPSERT LOGIC:
    - Finds existing log by (job_id + target_id)
    - If found: Updates status, error info, WhatsApp message ID, timestamps
    - If not found: Creates new log entry

    This ensures logs created during queuing (status='queued') are updated
    when the message is actually sent (status='success' or 'failure').
    """
    try:
        # Try to find existing log entry for this job + target
        existing_log = db.query(CampaignLog).filter(
            CampaignLog.job_id == job_id,
            CampaignLog.target_id == target_id
        ).first()

        now = datetime.utcnow()

        if existing_log:
            # Update existing record (queued -> success/failure)
            logger.debug(f"Updating existing log {existing_log.id}: {existing_log.status} -> {status}")

            existing_log.status = status
            existing_log.error_code = error_code
            existing_log.error_message = error_message
            existing_log.http_status_code = http_status_code
            existing_log.whatsapp_message_id = whatsapp_message_id
            existing_log.request_payload = request_payload
            existing_log.response_data = response_data
            existing_log.processing_time_ms = processing_time_ms
            existing_log.processed_at = now if status in ("success", "failure") else None

            # Track retries
            if existing_log.retry_count is None:
                existing_log.retry_count = 0
            existing_log.retry_count += 1
            existing_log.last_retry_at = now

            logger.info(f"📝 Log UPDATED: {phone_number} -> {status.upper()} (wa_msg_id: {whatsapp_message_id or 'N/A'})")
        else:
            # Create new record (should only happen if log wasn't created during queuing)
            log_entry = CampaignLog(
                campaign_id=campaign_id,
                job_id=job_id,
                target_type=target_type,
                target_id=target_id,
                phone_number=phone_number,
                status=status,
                error_code=error_code,
                error_message=error_message,
                http_status_code=http_status_code,
                whatsapp_message_id=whatsapp_message_id,
                request_payload=request_payload,
                response_data=response_data,
                processing_time_ms=processing_time_ms,
                processed_at=now if status in ("success", "failure") else None
            )
            db.add(log_entry)
            logger.info(f"📝 Log CREATED: {phone_number} -> {status.upper()} (wa_msg_id: {whatsapp_message_id or 'N/A'})")

        db.commit()
        logger.debug(f"Campaign log committed for {phone_number}")

    except Exception as e:
        logger.error(f"❌ Failed to upsert campaign log for {phone_number}: {e}")
        db.rollback()


def log_whatsapp_api_call(
    db: Session,
    campaign_id,
    job_id,
    phone_number: str,
    request_url: str,
    request_payload: dict,
    request_headers: dict,
    response_status_code: int,
    response_body: dict,
    response_headers: dict,
    whatsapp_message_id: str,
    error_code: str,
    error_message: str,
    request_time: datetime,
    response_time: datetime,
    duration_ms: int
):
    """Log WhatsApp API request and response for debugging"""
    try:
        # Sanitize headers (remove auth token for security)
        safe_headers = {k: v for k, v in (request_headers or {}).items() if k.lower() != 'authorization'}
        safe_headers['authorization'] = 'Bearer ***REDACTED***'

        log_entry = WhatsAppAPILog(
            campaign_id=campaign_id,
            job_id=job_id,
            phone_number=phone_number,
            request_url=request_url,
            request_payload=request_payload,
            request_headers=safe_headers,
            response_status_code=response_status_code,
            response_body=response_body,
            response_headers=dict(response_headers) if response_headers else None,
            whatsapp_message_id=whatsapp_message_id,
            error_code=error_code,
            error_message=error_message,
            request_time=request_time,
            response_time=response_time,
            duration_ms=duration_ms
        )
        db.add(log_entry)
        db.commit()
        logger.debug(f"📋 API call logged for {phone_number}")
    except Exception as e:
        logger.error(f"Failed to log WhatsApp API call: {e}")
        db.rollback()


def callback(ch, method, properties, body):
    """
    Process a single message from the queue.
    FIXES:
    - Proper DB session management with context manager
    - Detailed error logging
    - Rate limiting
    - Token refresh
    """
    delivery_tag = method.delivery_tag
    logger.info(f"📥 Received message from queue (delivery_tag={delivery_tag})")
    start_time = time.time()

    # Parse message
    try:
        task = json.loads(body)
    except Exception as e:
        logger.error(f"❌ Failed to parse message body: {e}")
        ch.basic_ack(delivery_tag=delivery_tag)
        return

    job_id = task.get("job_id")
    campaign_id = task.get("campaign_id")
    target_type = task.get("target_type")  # "recipient" | "customer"
    target_id = task.get("target_id")

    logger.info(f"📋 Processing: Campaign={campaign_id[:8]}..., Target={target_type}:{target_id[:8]}...")

    # Use context manager for proper session handling
    with get_db_session() as db:
        status = "failure"
        wa_id = None
        payload = None
        response_data = None
        http_status_code = None
        whatsapp_message_id = None
        error_code = None
        error_message = None

        try:
            # Parse UUIDs
            job_id_uuid = parse_uuid(job_id)
            campaign_id_uuid = parse_uuid(campaign_id)
            target_id_uuid = parse_uuid(target_id)

            # Load job and campaign
            job = db.query(Job).filter_by(id=job_id_uuid).first()
            campaign = db.query(Campaign).filter_by(id=campaign_id_uuid).first()

            if not campaign:
                error_message = f"Campaign {campaign_id} not found"
                logger.error(f"[CONSUMER ERROR] {error_message}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Check if campaign is stopped - skip processing
            if campaign.status == "stopped":
                logger.info(f"⏹️ Campaign {campaign_id[:8]} is stopped, skipping message")
                # Update recipient back to PENDING
                if target_type == "recipient":
                    target = db.query(CampaignRecipient).filter_by(id=target_id_uuid).first()
                    if target and target.status == "QUEUED":
                        target.status = "PENDING"
                        db.commit()
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Load target
            if target_type == "recipient":
                target = db.query(CampaignRecipient).filter_by(id=target_id_uuid).first()
                if not target:
                    error_message = f"Recipient {target_id} not found"
                    logger.error(f"[CONSUMER ERROR] {error_message}")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return
                wa_id = target.phone_number
            else:
                target = db.query(Customer).filter_by(id=target_id_uuid).first()
                if not target:
                    error_message = f"Customer {target_id} not found"
                    logger.error(f"[CONSUMER ERROR] {error_message}")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return
                wa_id = target.wa_id

            if not wa_id:
                error_code = "NO_PHONE"
                error_message = f"No wa_id/phone for target {target_type}:{target_id}"
                logger.error(f"[CONSUMER ERROR] {error_message}")

                # Log the failure
                upsert_campaign_log(
                    db, campaign_id_uuid, job_id_uuid, target_type, target_id_uuid,
                    wa_id or "unknown", "failure", error_code, error_message
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # Get token with refresh handling
            token = get_token_with_refresh(db)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            # Build payload based on campaign type
            if campaign.type == "template":
                if target_type == "recipient":
                    try:
                        recipient_params = target.params if target.params else {}
                        if not isinstance(recipient_params, dict):
                            try:
                                recipient_params = json.loads(recipient_params) if isinstance(recipient_params, str) else {}
                            except:
                                recipient_params = {}

                        recipient_dict = {
                            "phone_number": target.phone_number,
                            "name": target.name,
                            "params": recipient_params
                        }
                        payload = whatsapp_service.build_template_payload_for_recipient(
                            recipient_dict, campaign.content
                        )
                    except Exception as payload_err:
                        import traceback
                        logger.error(f"❌ Failed to build payload for recipient {target.id}: {payload_err}")
                        logger.error(f"   Traceback: {traceback.format_exc()}")
                        logger.error(f"   Recipient params: {recipient_params}")
                        raise  # Re-raise to be caught by outer exception handler
                else:
                    customer_dict = {
                        "wa_id": target.wa_id,
                        "name": target.name or ""
                    }
                    payload = whatsapp_service.build_template_payload(
                        customer_dict, campaign.content
                    )
            else:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": wa_id,
                    "recipient_type": "individual",
                    "type": campaign.type,
                    campaign.type: campaign.content,
                }

            # Rate limiting delay
            time.sleep(RATE_LIMIT_DELAY_MS / 1000.0)

            # Get HTTP session with connection pooling
            session = get_http_session()

            # Track API call timing
            api_request_time = datetime.utcnow()
            api_response_time = None
            api_duration_ms = 0
            response_headers_dict = None

            # Send request with retry logic
            for attempt in range(MAX_RETRIES):
                try:
                    api_request_time = datetime.utcnow()
                    res = session.post(WHATSAPP_API_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
                    api_response_time = datetime.utcnow()
                    api_duration_ms = int((api_response_time - api_request_time).total_seconds() * 1000)
                    http_status_code = res.status_code
                    response_headers_dict = dict(res.headers)

                    if res.status_code == 200:
                        status = "success"
                        try:
                            response_data = res.json()
                            # Extract WhatsApp message ID if available
                            messages = response_data.get("messages", [])
                            if messages:
                                whatsapp_message_id = messages[0].get("id")
                        except:
                            pass
                        break
                    elif res.status_code == 429:  # Rate limited
                        logger.warning(f"Rate limited, waiting {RETRY_DELAY_SECONDS}s before retry")
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    elif res.status_code == 401:  # Token expired
                        logger.warning("Token expired, refreshing...")
                        _token_cache["token"] = None  # Force refresh
                        token = get_token_with_refresh(db)
                        headers["Authorization"] = f"Bearer {token}"
                        continue
                    else:
                        try:
                            error_json = res.json()
                            error_code = str(error_json.get("error", {}).get("code", res.status_code))
                            error_message = error_json.get("error", {}).get("message", res.text[:500])
                            response_data = error_json
                        except:
                            error_code = str(res.status_code)
                            error_message = res.text[:500]
                        break

                except requests.exceptions.Timeout:
                    api_response_time = datetime.utcnow()
                    api_duration_ms = int((api_response_time - api_request_time).total_seconds() * 1000)
                    error_code = "TIMEOUT"
                    error_message = f"Request timeout on attempt {attempt + 1}"
                    logger.warning(error_message)
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                except requests.exceptions.RequestException as e:
                    api_response_time = datetime.utcnow()
                    api_duration_ms = int((api_response_time - api_request_time).total_seconds() * 1000)
                    error_code = "REQUEST_ERROR"
                    error_message = str(e)[:500]
                    logger.error(f"Request error: {e}")
                    break

            # Log the API call for debugging
            try:
                log_whatsapp_api_call(
                    db=db,
                    campaign_id=campaign_id_uuid,
                    job_id=job_id_uuid,
                    phone_number=wa_id,
                    request_url=WHATSAPP_API_URL,
                    request_payload=payload,
                    request_headers=headers,
                    response_status_code=http_status_code,
                    response_body=response_data,
                    response_headers=response_headers_dict,
                    whatsapp_message_id=whatsapp_message_id,
                    error_code=error_code,
                    error_message=error_message,
                    request_time=api_request_time,
                    response_time=api_response_time,
                    duration_ms=api_duration_ms
                )
            except Exception as log_err:
                logger.error(f"Failed to log API call: {log_err}")

        except Exception as e:
            import traceback
            error_code = "EXCEPTION"
            error_message = str(e)[:500]
            logger.error(f"Exception processing {target_type}:{target_id} - {e}")
            logger.error(traceback.format_exc())

        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Update DB statuses
        try:
            if target_type == "customer":
                job_status = db.query(JobStatus).filter_by(
                    job_id=job_id_uuid, customer_id=target_id_uuid
                ).first()
                if job_status:
                    job_status.status = status

            if target_type == "recipient":
                recipient = db.query(CampaignRecipient).filter_by(id=target_id_uuid).first()
                if recipient:
                    recipient.status = "SENT" if status == "success" else "FAILED"

            # Update job and campaign timestamps
            if job:
                job.last_triggered_time = datetime.utcnow()
            if campaign:
                campaign.last_job_id = job_id_uuid

            # Upsert detailed log entry (update if exists, create if not)
            upsert_campaign_log(
                db=db,
                campaign_id=campaign_id_uuid,
                job_id=job_id_uuid,
                target_type=target_type,
                target_id=target_id_uuid,
                phone_number=wa_id or "unknown",
                status=status,
                error_code=error_code,
                error_message=error_message,
                http_status_code=http_status_code,
                whatsapp_message_id=whatsapp_message_id,
                request_payload=payload,
                response_data=response_data,
                processing_time_ms=processing_time_ms
            )

            # Save campaign message to Message table for conversation view (only on success)
            if status == "success" and campaign.type == "template" and wa_id:
                try:
                    # Get or create customer
                    customer = customer_service.get_or_create_customer(
                        db, CustomerCreate(wa_id=wa_id, name=target.name if hasattr(target, 'name') else "")
                    )
                    
                    # Get business number (from_wa_id) - default to env or common number
                    from_wa_id = os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376")
                    
                    # Format template message body for display - show only template name
                    template_name = campaign.content.get("name", "Template") if isinstance(campaign.content, dict) else "Template"
                    template_body = f"📋 {template_name}"
                    
                    # Create message entry
                    message_data = MessageCreate(
                        message_id=whatsapp_message_id or f"campaign_{campaign_id_uuid}_{wa_id}_{int(time.time())}",
                        from_wa_id=from_wa_id,
                        to_wa_id=wa_id,
                        type="template",
                        body=template_body,
                        timestamp=datetime.utcnow(),
                        customer_id=customer.id,
                        agent_id=None,  # Campaign messages are system-sent
                        sender_type="agent",  # Show as agent message (right side)
                    )
                    message_service.create_message(db, message_data)
                    logger.info(f"💬 Saved campaign template message to conversation for {wa_id}")
                except Exception as msg_err:
                    # Don't fail the campaign if message save fails
                    logger.error(f"Failed to save campaign message to conversation: {msg_err}")

            db.commit()
            logger.info(f"[{status.upper()}] {target_type}:{wa_id} - {processing_time_ms}ms")

        except Exception as e:
            logger.error(f"Failed to update database: {e}")
            db.rollback()

    ch.basic_ack(delivery_tag=method.delivery_tag)


def start_worker(worker_id: int = 1):
    """Start a single RabbitMQ consumer worker"""
    logger.info(f"🚀 Campaign Worker {worker_id} started — prefetch={PREFETCH_COUNT}, rate_limit={RATE_LIMIT_DELAY_MS}ms")

    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host="localhost",
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            )
            channel = connection.channel()

            # Check queue status before consuming
            queue_state = channel.queue_declare(queue="campaign_queue", durable=True, passive=False)
            msg_count = queue_state.method.message_count
            consumer_count = queue_state.method.consumer_count
            logger.info(f"Worker {worker_id}: Queue status - messages={msg_count}, consumers={consumer_count}")

            # Use configurable prefetch count for better throughput
            channel.basic_qos(prefetch_count=PREFETCH_COUNT)
            channel.basic_consume(queue="campaign_queue", on_message_callback=callback)

            logger.info(f"Worker {worker_id}: Connected to RabbitMQ, waiting for messages...")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Worker {worker_id}: RabbitMQ connection error: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info(f"Worker {worker_id}: Stopped by user")
            break
        except Exception as e:
            logger.error(f"Worker {worker_id}: Unexpected error: {e}. Retrying in 5 seconds...")
            time.sleep(5)


def start_multi_worker(num_workers: int = 4):
    """
    Start multiple consumer workers using threading for high throughput.

    For 50,000 messages with 4 workers:
    - Each worker: ~33 msg/sec
    - Total: ~130 msg/sec
    - Estimated time: ~6-7 minutes
    """
    import threading

    logger.info(f"🚀 Starting {num_workers} campaign workers for high-volume processing...")
    logger.info(f"   Config: prefetch={PREFETCH_COUNT}, rate_limit={RATE_LIMIT_DELAY_MS}ms/msg")
    logger.info(f"   Estimated throughput: ~{num_workers * (1000 // RATE_LIMIT_DELAY_MS)} msg/sec")

    threads = []
    for i in range(num_workers):
        t = threading.Thread(target=start_worker, args=(i + 1,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)  # Stagger worker starts

    # Wait for all threads (or until interrupted)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("Shutting down all workers...")


if __name__ == "__main__":
    import sys

    # Parse command line arguments
    num_workers = 1
    if len(sys.argv) > 1:
        try:
            num_workers = int(sys.argv[1])
        except ValueError:
            pass

    if num_workers > 1:
        start_multi_worker(num_workers)
    else:
        start_worker()
