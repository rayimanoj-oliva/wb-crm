import json
import logging
from contextlib import contextmanager

import pika
import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.models import (
    Campaign,
    Customer,
    Template,
    Job,
    JobStatus,
    Cost,
    campaign_customers,
    CampaignRecipient,
    User,
    CampaignLog,
)
from sqlalchemy import func, case, and_, or_, desc, cast, String
from datetime import datetime, date
from io import BytesIO
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple
from schemas.campaign_schema import CampaignCreate, CampaignUpdate
from uuid import UUID

# Configure logging
logger = logging.getLogger(__name__)


# ------------------------------
# RabbitMQ Connection Manager (Fixes Connection Leak)
# ------------------------------

class RabbitMQConnectionManager:
    """Manages RabbitMQ connections efficiently to prevent connection leaks"""

    _instance = None
    _connection = None
    _channel = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_connection(self):
        """Get or create a RabbitMQ connection"""
        if self._connection is None or self._connection.is_closed:
            try:
                self._connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host="localhost",
                        heartbeat=600,
                        blocked_connection_timeout=300
                    )
                )
                logger.info("RabbitMQ connection established")
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ: {e}")
                raise
        return self._connection

    def get_channel(self, queue_name: str = "campaign_queue"):
        """Get or create a channel with queue declaration"""
        try:
            connection = self.get_connection()
            if self._channel is None or self._channel.is_closed:
                self._channel = connection.channel()
                self._channel.queue_declare(queue=queue_name, durable=True)
                logger.info(f"RabbitMQ channel created for queue: {queue_name}")
            return self._channel
        except Exception as e:
            logger.error(f"Failed to get RabbitMQ channel: {e}")
            # Reset connection on error
            self._connection = None
            self._channel = None
            raise

    def close(self):
        """Close the connection"""
        try:
            if self._channel and not self._channel.is_closed:
                self._channel.close()
            if self._connection and not self._connection.is_closed:
                self._connection.close()
            logger.info("RabbitMQ connection closed")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")
        finally:
            self._connection = None
            self._channel = None


# Global connection manager instance
rabbitmq_manager = RabbitMQConnectionManager()



def get_all_campaigns(db: Session, skip: int = 0, limit: int = 50, search: str = None, include_jobs: bool = True):
    """Get all campaigns with pagination, optional search, and job details."""
    query = db.query(Campaign)

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Campaign.name.ilike(search_term)) |
            (Campaign.description.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()

    # Apply pagination with ordering by created_at desc
    campaigns = query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()

    if not include_jobs:
        return {"items": campaigns, "total": total, "skip": skip, "limit": limit}

    # Build detailed campaign data with jobs
    campaign_items = []
    campaign_ids = [c.id for c in campaigns]

    # Fetch all jobs for these campaigns in one query
    jobs_by_campaign = {}
    if campaign_ids:
        all_jobs = db.query(Job).filter(Job.campaign_id.in_(campaign_ids)).order_by(Job.created_at.desc()).all()
        for job in all_jobs:
            if job.campaign_id not in jobs_by_campaign:
                jobs_by_campaign[job.campaign_id] = []
            jobs_by_campaign[job.campaign_id].append(job)

    # Fetch all campaign logs (statuses) in one query - use CampaignLog instead of JobStatus
    job_ids = [j.id for jobs in jobs_by_campaign.values() for j in jobs]
    statuses_by_job = {}
    if job_ids:
        all_logs = db.query(CampaignLog).filter(CampaignLog.job_id.in_(job_ids)).all()
        for log in all_logs:
            if log.job_id not in statuses_by_job:
                statuses_by_job[log.job_id] = []
            statuses_by_job[log.job_id].append(log)

    # Build response with jobs and stats
    for campaign in campaigns:
        campaign_data = {
            "id": str(campaign.id),
            "name": campaign.name,
            "description": campaign.description,
            "type": campaign.type,
            "content": campaign.content,
            "campaign_cost_type": campaign.campaign_cost_type,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
            "created_by": str(campaign.created_by) if campaign.created_by else None,
            "jobs": []
        }

        # Add jobs for this campaign
        campaign_jobs = jobs_by_campaign.get(campaign.id, [])
        for job in campaign_jobs:
            job_statuses = statuses_by_job.get(job.id, [])

            # Calculate stats
            stats = {"total": 0, "success": 0, "failure": 0, "pending": 0}
            statuses_list = []
            for s in job_statuses:
                stats["total"] += 1
                if s.status == "success":
                    stats["success"] += 1
                elif s.status == "failure":
                    stats["failure"] += 1
                elif s.status == "pending":
                    stats["pending"] += 1

                statuses_list.append({
                    "target_id": str(s.target_id) if s.target_id else None,
                    "phone_number": s.phone_number,
                    "status": s.status,
                    "error_message": s.error_message
                })

            job_data = {
                "id": str(job.id),
                "campaign_id": str(job.campaign_id),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "last_attempted_by": str(job.last_attempted_by) if job.last_attempted_by else None,
                "last_triggered_time": job.last_triggered_time.isoformat() if job.last_triggered_time else None,
                "statuses": statuses_list,
                "stats": stats
            }
            campaign_data["jobs"].append(job_data)

        campaign_items.append(campaign_data)

    return {"items": campaign_items, "total": total, "skip": skip, "limit": limit}

def get_campaign(db: Session, campaign_id: UUID):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

def create_campaign(db: Session, campaign: CampaignCreate, user_id: UUID):
    new_campaign = Campaign(
        name=campaign.name,
        description=campaign.description,
        content=campaign.content,
        type=campaign.type,
        campaign_cost_type=campaign.campaign_cost_type,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(new_campaign)

    # Validate and link customers
    if campaign.customer_ids:
        found_customers = db.query(Customer).filter(Customer.id.in_(campaign.customer_ids)).all()
        found_ids = {c.id for c in found_customers}
        missing_ids = [str(cid) for cid in campaign.customer_ids if cid not in found_ids]

        if missing_ids:
            logger.warning(f"Campaign {new_campaign.name}: {len(missing_ids)} customer IDs not found: {missing_ids[:5]}...")

        new_campaign.customers = found_customers

    db.commit()
    db.refresh(new_campaign)

    # Log campaign creation
    logger.info(f"Campaign created: {new_campaign.id} with {len(new_campaign.customers)} customers")

    return new_campaign

def update_campaign(db: Session, campaign_id: UUID, updates: CampaignUpdate, user_id: UUID):
    campaign = get_campaign(db, campaign_id)

    for field, value in updates.dict(exclude_unset=True).items():
        if field == "customer_ids":
            campaign.customers = db.query(Customer).filter(Customer.id.in_(value)).all()
        else:
            setattr(campaign, field, value)
    campaign.updated_by = user_id
    db.commit()
    db.refresh(campaign)
    return campaign

def delete_campaign(db: Session, campaign_id: UUID):
    campaign = get_campaign(db, campaign_id)
    db.delete(campaign)
    db.commit()
    return {"detail": "Campaign deleted"}

import uuid as uuid_module

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, uuid_module.UUID):
            return str(o)
        return super().default(o)


def validate_phone_number(phone: str) -> bool:
    """Basic phone number validation"""
    if not phone:
        return False
    # Remove common prefixes and check length
    cleaned = phone.replace("+", "").replace(" ", "").replace("-", "")
    return len(cleaned) >= 10 and cleaned.isdigit()


def publish_to_queue(message: dict, queue_name: str = "campaign_queue"):
    """
    Publish a message to RabbitMQ queue using connection manager.
    FIXED: Now uses single connection instead of creating new one per message.
    """
    try:
        channel = rabbitmq_manager.get_channel(queue_name)
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message, cls=EnhancedJSONEncoder),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        return True
    except Exception as e:
        logger.error(f"Failed to publish message to queue: {e}")
        # Try to reconnect on next call
        rabbitmq_manager._connection = None
        rabbitmq_manager._channel = None
        raise


def publish_batch_to_queue(
    messages: List[dict],
    queue_name: str = "campaign_queue",
    chunk_size: int = 1000,
    log_progress: bool = True
) -> Tuple[int, int]:
    """
    Publish multiple messages to RabbitMQ queue efficiently with chunked processing.

    Optimized for high volume (50,000+ messages):
    - Processes in chunks to prevent memory issues
    - Logs progress for monitoring
    - Reconnects on failure

    Returns (success_count, failure_count)
    """
    success_count = 0
    failure_count = 0
    total_messages = len(messages)

    if log_progress and total_messages > 1000:
        logger.info(f"📤 Starting batch publish of {total_messages:,} messages in chunks of {chunk_size}")

    try:
        channel = rabbitmq_manager.get_channel(queue_name)
        properties = pika.BasicProperties(delivery_mode=2)

        for i in range(0, total_messages, chunk_size):
            chunk = messages[i:i + chunk_size]
            chunk_success = 0
            chunk_failure = 0

            for message in chunk:
                try:
                    channel.basic_publish(
                        exchange='',
                        routing_key=queue_name,
                        body=json.dumps(message, cls=EnhancedJSONEncoder),
                        properties=properties
                    )
                    chunk_success += 1
                except Exception as e:
                    logger.error(f"Failed to publish message: {e}")
                    chunk_failure += 1
                    # Try to reconnect on channel errors
                    try:
                        channel = rabbitmq_manager.get_channel(queue_name)
                    except:
                        pass

            success_count += chunk_success
            failure_count += chunk_failure

            # Log progress for large batches
            if log_progress and total_messages > 1000:
                progress = min(i + chunk_size, total_messages)
                percent = (progress / total_messages) * 100
                logger.info(f"📤 Progress: {progress:,}/{total_messages:,} ({percent:.1f}%) - Success: {success_count:,}, Failed: {failure_count}")

        if log_progress and total_messages > 1000:
            logger.info(f"✅ Batch publish complete: {success_count:,} queued, {failure_count} failed")

        return success_count, failure_count

    except Exception as e:
        logger.error(f"Failed to get RabbitMQ channel for batch publish: {e}")
        return success_count, failure_count + (total_messages - success_count - failure_count)


def run_campaign(
    campaign: Campaign,
    job: Job,
    db: Session,
    *,
    batch_size: int = 0,
    batch_delay: int = 0,
    log_batch_size: int = 500,  # Commit logs in batches for large campaigns
):
    """
    Run a campaign by queuing messages to RabbitMQ.

    OPTIMIZED for high volume (50,000+ messages):
    - Uses single connection for all messages (no connection leak)
    - Adds deduplication check
    - Creates CampaignLog entries in batches for performance
    - Validates phone numbers before queuing
    - Supports batch_size and batch_delay for throttling
    - Progress logging for large campaigns
    """
    from models.models import CampaignRecipient, CampaignLog
    import time as time_module

    start_time = time_module.time()

    recipients = db.query(CampaignRecipient).filter_by(campaign_id=campaign.id).all()
    messages_to_queue = []
    logs_to_create = []
    skipped_count = 0
    invalid_phone_count = 0
    duplicate_count = 0

    if recipients:
        total_recipients = len(recipients)
        is_large_campaign = total_recipients > 1000

        if is_large_campaign:
            logger.info(f"🚀 HIGH-VOLUME Campaign {campaign.id}: {total_recipients:,} recipients - starting queue process")
        else:
            logger.info(f"Campaign {campaign.id} has {total_recipients} recipients - preparing to queue")

        # Track processed phone numbers to prevent duplicates
        processed_phones = set()

        for idx, r in enumerate(recipients):
            # Skip already processed (SENT/FAILED) recipients - deduplication
            if r.status in ("SENT", "FAILED"):
                skipped_count += 1
                continue

            # Validate phone number
            if not validate_phone_number(r.phone_number):
                invalid_phone_count += 1
                r.status = "FAILED"
                # Create log entry for invalid phone
                logs_to_create.append(CampaignLog(
                    campaign_id=campaign.id,
                    job_id=job.id,
                    target_type="recipient",
                    target_id=r.id,
                    phone_number=r.phone_number,
                    status="failure",
                    error_code="INVALID_PHONE",
                    error_message=f"Invalid phone number format: {r.phone_number}",
                    created_at=datetime.utcnow()
                ))
                continue

            # Deduplication within this batch
            if r.phone_number in processed_phones:
                duplicate_count += 1
                continue
            processed_phones.add(r.phone_number)

            task = {
                "job_id": str(job.id),
                "campaign_id": str(campaign.id),
                "target_type": "recipient",
                "target_id": str(r.id),
                "batch_size": batch_size,
                "batch_delay": batch_delay,
            }
            messages_to_queue.append((task, r))

            # Create queued log entry
            logs_to_create.append(CampaignLog(
                campaign_id=campaign.id,
                job_id=job.id,
                target_type="recipient",
                target_id=r.id,
                phone_number=r.phone_number,
                status="queued",
                created_at=datetime.utcnow()
            ))

        # Batch publish all messages
        if messages_to_queue:
            success, failure = publish_batch_to_queue([m[0] for m in messages_to_queue])

            # Update recipient statuses
            for task, recipient in messages_to_queue:
                recipient.status = "QUEUED"

        # Save logs in batches for large campaigns
        if logs_to_create:
            if is_large_campaign:
                # Batch commit logs for better performance
                for i in range(0, len(logs_to_create), log_batch_size):
                    batch = logs_to_create[i:i + log_batch_size]
                    db.add_all(batch)
                    db.flush()  # Flush but don't commit yet
            else:
                db.add_all(logs_to_create)

        db.commit()

        # Log summary for large campaigns
        elapsed = time_module.time() - start_time
        queued_count = len(messages_to_queue)
        if is_large_campaign:
            logger.info(f"✅ Campaign {campaign.id} queuing complete in {elapsed:.1f}s:")
            logger.info(f"   📤 Queued: {queued_count:,}")
            logger.info(f"   ⏭️  Skipped (already sent): {skipped_count:,}")
            logger.info(f"   🔄 Duplicates removed: {duplicate_count:,}")
            logger.info(f"   ❌ Invalid phones: {invalid_phone_count}")
            logger.info(f"   ⏱️  Estimated send time: ~{max(1, queued_count // (80 * 60))} minutes (Meta limit: 80 msg/sec)")
        else:
            logger.info(f"Queued {queued_count} messages, {skipped_count} skipped, {invalid_phone_count} invalid")

        return job

    # No recipients → normal CRM customers
    total_customers = len(campaign.customers)
    is_large_campaign = total_customers > 1000

    if is_large_campaign:
        logger.info(f"🚀 HIGH-VOLUME Campaign {campaign.id}: {total_customers:,} customers - starting queue process")
    else:
        logger.info(f"Campaign {campaign.id} has {total_customers} customers - preparing to queue")

    processed_wa_ids = set()

    for c in campaign.customers:
        # Validate wa_id
        if not validate_phone_number(c.wa_id):
            invalid_phone_count += 1
            logs_to_create.append(CampaignLog(
                campaign_id=campaign.id,
                job_id=job.id,
                target_type="customer",
                target_id=c.id,
                phone_number=c.wa_id,
                status="failure",
                error_code="INVALID_PHONE",
                error_message=f"Invalid wa_id format: {c.wa_id}",
                created_at=datetime.utcnow()
            ))
            continue

        # Deduplication
        if c.wa_id in processed_wa_ids:
            duplicate_count += 1
            continue
        processed_wa_ids.add(c.wa_id)

        task = {
            "job_id": str(job.id),
            "campaign_id": str(campaign.id),
            "target_type": "customer",
            "target_id": str(c.id),
            "batch_size": batch_size,
            "batch_delay": batch_delay,
        }
        messages_to_queue.append(task)

        logs_to_create.append(CampaignLog(
            campaign_id=campaign.id,
            job_id=job.id,
            target_type="customer",
            target_id=c.id,
            phone_number=c.wa_id,
            status="queued",
            created_at=datetime.utcnow()
        ))

    # Batch publish
    if messages_to_queue:
        success, failure = publish_batch_to_queue(messages_to_queue)

    # Save logs in batches for large campaigns
    if logs_to_create:
        if is_large_campaign:
            for i in range(0, len(logs_to_create), log_batch_size):
                batch = logs_to_create[i:i + log_batch_size]
                db.add_all(batch)
                db.flush()
        else:
            db.add_all(logs_to_create)

    db.commit()

    # Log summary
    elapsed = time_module.time() - start_time
    queued_count = len(messages_to_queue)
    if is_large_campaign:
        logger.info(f"✅ Campaign {campaign.id} queuing complete in {elapsed:.1f}s:")
        logger.info(f"   📤 Queued: {queued_count:,}")
        logger.info(f"   🔄 Duplicates removed: {duplicate_count:,}")
        logger.info(f"   ❌ Invalid phones: {invalid_phone_count}")
        logger.info(f"   ⏱️  Estimated send time: ~{max(1, queued_count // (80 * 60))} minutes (Meta limit: 80 msg/sec)")
    else:
        logger.info(f"Queued {queued_count} customer messages, {duplicate_count} duplicates, {invalid_phone_count} invalid")

    return job


# ------------------------------
# Campaign Reports Aggregation
# ------------------------------

def _date_from_str(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Accept YYYY-MM-DD; interpret as whole day range in controller
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _build_campaign_base_query(
    db: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    type_filter: Optional[str] = None,
    campaign_id: Optional[str] = None,
    search: Optional[str] = None,
):
    query = db.query(Campaign)

    if from_date:
        query = query.filter(Campaign.created_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(Campaign.created_at <= datetime.combine(to_date, datetime.max.time()))
    if type_filter:
        query = query.filter(Campaign.type == type_filter)
    if campaign_id:
        query = query.filter(Campaign.id == campaign_id)
    if search:
        like = f"%{search}%"
        # Match name, description, template name inside content JSON if present
        conditions = [Campaign.name.ilike(like), Campaign.description.ilike(like)]
        try:
            from sqlalchemy.dialects.postgresql import JSONB
            conditions.append(Campaign.content["name"].astext.ilike(like))
        except Exception:
            pass
        query = query.filter(or_(*conditions))
    return query


def _aggregations_subqueries(db: Session):
    # Campaign log aggregation per campaign (using CampaignLog instead of JobStatus)
    job_status_agg = (
        db.query(
            CampaignLog.campaign_id.label("campaign_id"),
            func.sum(case((CampaignLog.status == "success", 1), else_=0)).label("success_count"),
            func.sum(case((CampaignLog.status == "failure", 1), else_=0)).label("failure_count"),
            func.sum(case(
                (CampaignLog.status == "pending", 1),
                (CampaignLog.status == "queued", 1),
                else_=0
            )).label("pending_count"),
            func.max(CampaignLog.processed_at).label("last_processed"),
        )
        .group_by(CampaignLog.campaign_id)
        .subquery()
    )

    # Customers count via M2M table
    cust_count_sq = (
        db.query(
            campaign_customers.c.campaign_id.label("campaign_id"),
            func.count(campaign_customers.c.customer_id).label("customers_count"),
        )
        .group_by(campaign_customers.c.campaign_id)
        .subquery()
    )

    # Uploaded recipients count
    recip_count_sq = (
        db.query(
            CampaignRecipient.campaign_id.label("campaign_id"),
            func.count(CampaignRecipient.id).label("recipients_count"),
        )
        .group_by(CampaignRecipient.campaign_id)
        .subquery()
    )

    # Latest job per campaign to fetch last_attempted_by and last_triggered_time
    last_time = func.coalesce(Job.last_triggered_time, Job.created_at).label("last_time")
    rn = func.row_number().over(partition_by=Job.campaign_id, order_by=desc(last_time)).label("rn")
    ranked = (
        db.query(
            Job.campaign_id.label("campaign_id"),
            Job.last_attempted_by.label("last_attempted_by"),
            Job.last_triggered_time.label("last_triggered_time"),
            Job.created_at.label("job_created_at"),
            last_time,
            rn,
        )
    ).subquery()

    last_job_sq = (
        db.query(
            ranked.c.campaign_id,
            ranked.c.last_attempted_by,
            ranked.c.last_triggered_time,
            ranked.c.job_created_at
        )
        .filter(ranked.c.rn == 1)
        .subquery()
    )

    return job_status_agg, cust_count_sq, recip_count_sq, last_job_sq


def get_campaign_reports(
    db: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    type_filter: Optional[str] = None,
    campaign_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    base_q = _build_campaign_base_query(
        db,
        from_date=from_date,
        to_date=to_date,
        type_filter=type_filter,
        campaign_id=campaign_id,
        search=search,
    )

    job_agg, cust_sq, recip_sq, last_job_sq = _aggregations_subqueries(db)

    q = (
        base_q
        .outerjoin(job_agg, job_agg.c.campaign_id == Campaign.id)
        .outerjoin(cust_sq, cust_sq.c.campaign_id == Campaign.id)
        .outerjoin(recip_sq, recip_sq.c.campaign_id == Campaign.id)
        .outerjoin(Cost, Cost.type == Campaign.campaign_cost_type)
        .outerjoin(User, User.id == Campaign.created_by)
        .outerjoin(last_job_sq, last_job_sq.c.campaign_id == Campaign.id)
        .add_columns(
            job_agg.c.success_count,
            job_agg.c.failure_count,
            job_agg.c.pending_count,
            job_agg.c.last_processed,
            cust_sq.c.customers_count,
            recip_sq.c.recipients_count,
            Cost.price,
            User.first_name,
            User.last_name,
            User.username,
            last_job_sq.c.last_attempted_by,
            last_job_sq.c.last_triggered_time,
            last_job_sq.c.job_created_at,
        )
    )

    rows = []
    for campaign, success_count, failure_count, pending_count, last_processed, customers_count, recipients_count, price, ufn, uln, uname, last_attempted_by, last_triggered_time, job_created_at in q.all():
        # Use last_processed (from CampaignLog) or fall back to job's last_triggered_time or job creation time
        last_triggered = last_processed or last_triggered_time or job_created_at
        success_count = int(success_count or 0)
        failure_count = int(failure_count or 0)
        pending_count = int(pending_count or 0)
        customers_count = int(customers_count or 0)
        recipients_count = int(recipients_count or 0)
        total_recipients = customers_count + recipients_count
        denom = total_recipients if total_recipients > 0 else (success_count + failure_count + pending_count)
        denom = denom or 1
        success_rate = round((success_count / denom) * 100, 2)
        failure_rate = round((failure_count / denom) * 100, 2)
        pending_rate = round((pending_count / denom) * 100, 2)
        total_cost = float(price or 0) * float(total_recipients)

        template_name = None
        try:
            if isinstance(campaign.content, dict):
                template_name = campaign.content.get("name")
        except Exception:
            pass

        created_by_name = None
        try:
            fullname = " ".join([p for p in [ufn, uln] if p])
            created_by_name = fullname if fullname.strip() else uname
        except Exception:
            created_by_name = None

        rows.append({
            "id": str(campaign.id),
            "name": campaign.name,
            "description": campaign.description,
            "type": str(campaign.type),
            "template_name": template_name,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "created_by": str(campaign.created_by),
            "created_by_name": created_by_name,
            "total_recipients": total_recipients,
            "success_count": success_count,
            "failure_count": failure_count,
            "pending_count": pending_count,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "pending_rate": pending_rate,
            "total_cost": round(total_cost, 2),
            "last_triggered": last_triggered.isoformat() if last_triggered else None,
            "last_triggered_by": str(last_attempted_by) if last_attempted_by else None,
        })

    # Sorting
    key_map = {
        "name": lambda r: (r.get("name") or "").lower(),
        "created_at": lambda r: r.get("created_at") or "",
        "total_recipients": lambda r: r.get("total_recipients") or 0,
        "success_count": lambda r: r.get("success_count") or 0,
        "failure_count": lambda r: r.get("failure_count") or 0,
        "pending_count": lambda r: r.get("pending_count") or 0,
        "success_rate": lambda r: r.get("success_rate") or 0.0,
        "failure_rate": lambda r: r.get("failure_rate") or 0.0,
        "pending_rate": lambda r: r.get("pending_rate") or 0.0,
        "total_cost": lambda r: r.get("total_cost") or 0.0,
        "last_triggered": lambda r: r.get("last_triggered") or "",
    }
    if sort_by and sort_by in key_map:
        rows.sort(key=key_map[sort_by], reverse=(str(sort_dir).lower() == "desc"))

    # Pagination
    try:
        page = max(1, int(page))
        limit = max(1, int(limit))
    except Exception:
        page, limit = 1, 25
    start = (page - 1) * limit
    end = start + limit
    return rows[start:end]


def export_campaign_reports_excel(
    db: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    type_filter: Optional[str] = None,
    campaign_id: Optional[str] = None,
    search: Optional[str] = None,
) -> bytes:
    rows = get_campaign_reports(
        db,
        from_date=from_date,
        to_date=to_date,
        type_filter=type_filter,
        campaign_id=campaign_id,
        search=search,
        page=1,
        limit=10_000,
    )

    # Map to Excel columns in requested order
    export_rows = []
    for r in rows:
        export_rows.append({
            "Campaign Name": r.get("name"),
            "Description": r.get("description"),
            "Type": r.get("type"),
            "Template Name": r.get("template_name"),
            "Created Date": r.get("created_at"),
            "Created By": r.get("created_by_name") or r.get("created_by"),
            "Total Recipients": r.get("total_recipients"),
            "Success Count": r.get("success_count"),
            "Failure Count": r.get("failure_count"),
            "Pending Count": r.get("pending_count"),
            "Success Rate (% )": r.get("success_rate"),
            "Failure Rate (% )": r.get("failure_rate"),
            "Pending Rate (% )": r.get("pending_rate"),
            "Total Cost (₹)": r.get("total_cost"),
            "Last Triggered": r.get("last_triggered"),
            "Last Triggered By": r.get("last_triggered_by"),
        })
    df = pd.DataFrame(export_rows)
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Campaign Reports")
    bio.seek(0)
    return bio.read()


def get_single_campaign_report(db: Session, campaign_id: str) -> Dict[str, Any]:
    rows = get_campaign_reports(db, campaign_id=campaign_id, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Campaign not found or no data")
    summary = rows[0]

    # Per-job breakdown
    jobs = (
        db.query(
            Job.id,
            func.max(func.coalesce(Job.last_triggered_time, Job.created_at)).label("triggered_at"),
            func.sum(case((JobStatus.status == "success", 1), else_=0)).label("success_count"),
            func.sum(case((JobStatus.status == "failure", 1), else_=0)).label("failure_count"),
            func.sum(case((JobStatus.status == "pending", 1), else_=0)).label("pending_count"),
            func.max(User.first_name).label("first_name"),
            func.max(User.last_name).label("last_name"),
            func.max(User.username).label("username"),
            func.min(cast(Job.last_attempted_by, String)).label("last_attempted_by"),
        )
        .join(JobStatus, JobStatus.job_id == Job.id)
        .outerjoin(User, User.id == Job.last_attempted_by)
        .filter(Job.campaign_id == campaign_id)
        .group_by(Job.id)
        .order_by(desc("triggered_at"))
        .all()
    )
    job_rows = []
    for j in jobs:
        try:
            fullname = " ".join([p for p in [j.first_name, j.last_name] if p])
            triggered_by_name = fullname if fullname.strip() else j.username
        except Exception:
            triggered_by_name = None
        job_rows.append({
            "job_id": str(j.id),
            "triggered_at": j.triggered_at.isoformat() if j.triggered_at else None,
            "success_count": int(j.success_count or 0),
            "failure_count": int(j.failure_count or 0),
            "pending_count": int(j.pending_count or 0),
            "triggered_by_name": triggered_by_name,
            "triggered_by_id": str(j.last_attempted_by) if getattr(j, "last_attempted_by", None) else None,
        })

    return {"summary": summary, "jobs": job_rows}


def get_campaigns_running_in_date_range(
    db: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    type_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Campaigns that had a job triggered/created in the given date range."""
    # Base campaign filters excluding campaign_id
    base_q = _build_campaign_base_query(
        db,
        from_date=None,
        to_date=None,
        type_filter=type_filter,
        campaign_id=None,
        search=search,
    )

    job_agg, cust_sq, recip_sq, last_job_sq = _aggregations_subqueries(db)

    # Constrain by job activity window
    job_window = db.query(Job.campaign_id).filter(
        and_(
            (Job.last_triggered_time != None) | (Job.created_at != None),
            # Window condition: any job within [from_date, to_date]
            (Job.last_triggered_time.between(
                datetime.combine(from_date, datetime.min.time()) if from_date else datetime.min,
                datetime.combine(to_date, datetime.max.time()) if to_date else datetime.max,
            ))
            | (Job.created_at.between(
                datetime.combine(from_date, datetime.min.time()) if from_date else datetime.min,
                datetime.combine(to_date, datetime.max.time()) if to_date else datetime.max,
            )),
        )
    ).group_by(Job.campaign_id).subquery()

    q = (
        base_q
        .join(job_window, job_window.c.campaign_id == Campaign.id)
        .outerjoin(job_agg, job_agg.c.campaign_id == Campaign.id)
        .outerjoin(cust_sq, cust_sq.c.campaign_id == Campaign.id)
        .outerjoin(recip_sq, recip_sq.c.campaign_id == Campaign.id)
        .outerjoin(Cost, Cost.type == Campaign.campaign_cost_type)
        .outerjoin(last_job_sq, last_job_sq.c.campaign_id == Campaign.id)
        .add_columns(
            job_agg.c.success_count,
            job_agg.c.failure_count,
            job_agg.c.pending_count,
            job_agg.c.last_triggered,
            cust_sq.c.customers_count,
            recip_sq.c.recipients_count,
            Cost.price,
            last_job_sq.c.last_attempted_by,
        )
    )

    rows = []
    for campaign, success_count, failure_count, pending_count, last_triggered, customers_count, recipients_count, price, last_attempted_by in q.all():
        success_count = int(success_count or 0)
        failure_count = int(failure_count or 0)
        pending_count = int(pending_count or 0)
        customers_count = int(customers_count or 0)
        recipients_count = int(recipients_count or 0)
        total_recipients = customers_count + recipients_count
        denom = total_recipients if total_recipients > 0 else (success_count + failure_count + pending_count)
        denom = denom or 1
        success_rate = round((success_count / denom) * 100, 2)
        failure_rate = round((failure_count / denom) * 100, 2)
        pending_rate = round((pending_count / denom) * 100, 2)
        total_cost = float(price or 0) * float(total_recipients)

        template_name = None
        try:
            if isinstance(campaign.content, dict):
                template_name = campaign.content.get("name")
        except Exception:
            pass

        rows.append({
            "id": str(campaign.id),
            "name": campaign.name,
            "description": campaign.description,
            "type": str(campaign.type),
            "template_name": template_name,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "created_by": str(campaign.created_by),
            "total_recipients": total_recipients,
            "success_count": success_count,
            "failure_count": failure_count,
            "pending_count": pending_count,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "pending_rate": pending_rate,
            "total_cost": round(total_cost, 2),
            "last_triggered": last_triggered.isoformat() if last_triggered else None,
            "last_triggered_by": str(last_attempted_by) if last_attempted_by else None,
        })

    # Sorting and pagination reuse from get_campaign_reports
    key_map = {
        "name": lambda r: (r.get("name") or "").lower(),
        "created_at": lambda r: r.get("created_at") or "",
        "total_recipients": lambda r: r.get("total_recipients") or 0,
        "success_count": lambda r: r.get("success_count") or 0,
        "failure_count": lambda r: r.get("failure_count") or 0,
        "pending_count": lambda r: r.get("pending_count") or 0,
        "success_rate": lambda r: r.get("success_rate") or 0.0,
        "failure_rate": lambda r: r.get("failure_rate") or 0.0,
        "pending_rate": lambda r: r.get("pending_rate") or 0.0,
        "total_cost": lambda r: r.get("total_cost") or 0.0,
        "last_triggered": lambda r: r.get("last_triggered") or "",
    }
    if sort_by and sort_by in key_map:
        rows.sort(key=key_map[sort_by], reverse=(str(sort_dir).lower() == "desc"))

    try:
        page = max(1, int(page))
        limit = max(1, int(limit))
    except Exception:
        page, limit = 1, 25
    start = (page - 1) * limit
    end = start + limit
    return rows[start:end]


def export_single_campaign_report_excel(db: Session, campaign_id: str) -> bytes:
    data = get_single_campaign_report(db, campaign_id)
    summary = data.get("summary", {})
    jobs = data.get("jobs", [])

    # Build DataFrames
    import pandas as pd
    from io import BytesIO
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, index=False, sheet_name="Summary")
        pd.DataFrame(jobs).to_excel(writer, index=False, sheet_name="Jobs")
    bio.seek(0)
    return bio.read()
