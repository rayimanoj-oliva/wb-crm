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
    JobStatus, Campaign, Job, Customer, CampaignRecipient, CampaignLog
)
from services import whatsapp_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT_DELAY_MS = 100  # 100ms delay between messages (10 msg/sec)
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

# Token cache with expiry tracking
_token_cache = {
    "token": None,
    "fetched_at": None,
    "expires_in_seconds": 3600  # Assume 1 hour expiry
}


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
    """Create or update a log entry in campaign_logs table (upsert by job_id + target_id)"""
    try:
        # Try to find existing log entry for this job + target
        existing_log = db.query(CampaignLog).filter(
            CampaignLog.job_id == job_id,
            CampaignLog.target_id == target_id
        ).first()

        if existing_log:
            # Update existing record
            existing_log.status = status
            existing_log.error_code = error_code
            existing_log.error_message = error_message
            existing_log.http_status_code = http_status_code
            existing_log.whatsapp_message_id = whatsapp_message_id
            existing_log.request_payload = request_payload
            existing_log.response_data = response_data
            existing_log.processing_time_ms = processing_time_ms
            existing_log.processed_at = datetime.utcnow() if status in ("success", "failure") else None
            if existing_log.retry_count is None:
                existing_log.retry_count = 0
            existing_log.retry_count += 1
            existing_log.last_retry_at = datetime.utcnow()
        else:
            # Create new record
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
                processed_at=datetime.utcnow() if status in ("success", "failure") else None
            )
            db.add(log_entry)

        db.commit()
    except Exception as e:
        logger.error(f"Failed to upsert campaign log: {e}")
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
    logger.info("Received message from queue")
    start_time = time.time()

    # Parse message
    try:
        task = json.loads(body)
    except Exception as e:
        logger.error(f"Failed to parse message body: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    job_id = task.get("job_id")
    campaign_id = task.get("campaign_id")
    target_type = task.get("target_type")  # "recipient" | "customer"
    target_id = task.get("target_id")

    logger.info(f"Processing Job {job_id}, Campaign {campaign_id}, Target {target_type}:{target_id}")

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

            # Send request with retry logic
            for attempt in range(MAX_RETRIES):
                try:
                    res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers, timeout=30)
                    http_status_code = res.status_code

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
                    error_code = "TIMEOUT"
                    error_message = f"Request timeout on attempt {attempt + 1}"
                    logger.warning(error_message)
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                except requests.exceptions.RequestException as e:
                    error_code = "REQUEST_ERROR"
                    error_message = str(e)[:500]
                    logger.error(f"Request error: {e}")
                    break

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

            db.commit()
            logger.info(f"[{status.upper()}] {target_type}:{wa_id} - {processing_time_ms}ms")

        except Exception as e:
            logger.error(f"Failed to update database: {e}")
            db.rollback()

    ch.basic_ack(delivery_tag=method.delivery_tag)


def start_worker():
    """Start the RabbitMQ consumer worker"""
    logger.info("🚀 Campaign Worker started — listening for messages...")

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
            channel.queue_declare(queue="campaign_queue", durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue="campaign_queue", on_message_callback=callback)

            logger.info("Connected to RabbitMQ, waiting for messages...")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Retrying in 5 seconds...")
            time.sleep(5)


if __name__ == "__main__":
    start_worker()
