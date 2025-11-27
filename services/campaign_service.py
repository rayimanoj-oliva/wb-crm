import json

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
)
from sqlalchemy import func, case, and_, or_, desc, cast, String
from datetime import datetime, date
from io import BytesIO
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple
from schemas.campaign_schema import CampaignCreate, CampaignUpdate
from uuid import UUID



def get_all_campaigns(db: Session):
    return db.query(Campaign).all()

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

    if campaign.customer_ids:
        new_campaign.customers = db.query(Customer).filter(Customer.id.in_(campaign.customer_ids)).all()

    print(new_campaign.customers)
    db.commit()
    db.refresh(new_campaign)
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

import json
import uuid

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, uuid.UUID):
            return str(o)
        return super().default(o)

def publish_to_queue(message: dict, queue_name: str = "campaign_queue"):
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=queue_name,
        body=json.dumps(message,cls=EnhancedJSONEncoder),
        properties=pika.BasicProperties(
            delivery_mode=2,
        )
    )
    connection.close()

def run_campaign(
    campaign: Campaign,
    job: Job,
    db: Session,
    *,
    batch_size: int = 0,
    batch_delay: int = 0,
):
    from models.models import CampaignRecipient

    recipients = db.query(CampaignRecipient).filter_by(campaign_id=campaign.id).all()

    if recipients:
        print(f"[DEBUG] Campaign has {len(recipients)} recipients - queuing recipient IDs only")

        for idx, r in enumerate(recipients):
            task = {
                "job_id": str(job.id),
                "campaign_id": str(campaign.id),
                "target_type": "recipient",
                "target_id": str(r.id),
                "batch_size": batch_size,
                "batch_delay": batch_delay,
            }
            publish_to_queue(task)
            r.status = "QUEUED"

        db.commit()
        return job

    # No recipients → normal CRM customers
    print(f"[DEBUG] Campaign has {len(campaign.customers)} customers - queuing customer IDs only")

    for c in campaign.customers:
        task = {
            "job_id": str(job.id),
            "campaign_id": str(campaign.id),
            "target_type": "customer",
            "target_id": str(c.id),
            "batch_size": batch_size,
            "batch_delay": batch_delay,
        }
        publish_to_queue(task)

    db.commit()
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
    # Job status aggregation per campaign
    job_status_agg = (
        db.query(
            Job.campaign_id.label("campaign_id"),
            func.sum(case((JobStatus.status == "success", 1), else_=0)).label("success_count"),
            func.sum(case((JobStatus.status == "failure", 1), else_=0)).label("failure_count"),
            func.sum(case((JobStatus.status == "pending", 1), else_=0)).label("pending_count"),
            func.max(func.coalesce(Job.last_triggered_time, Job.created_at)).label("last_triggered"),
        )
        .join(JobStatus, JobStatus.job_id == Job.id)
        .group_by(Job.campaign_id)
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

    # Latest job per campaign to fetch last_attempted_by aligned with last_triggered
    last_time = func.coalesce(Job.last_triggered_time, Job.created_at).label("last_time")
    rn = func.row_number().over(partition_by=Job.campaign_id, order_by=desc(last_time)).label("rn")
    ranked = (
        db.query(
            Job.campaign_id.label("campaign_id"),
            Job.last_attempted_by.label("last_attempted_by"),
            last_time,
            rn,
        )
    ).subquery()

    last_job_sq = (
        db.query(ranked.c.campaign_id, ranked.c.last_attempted_by)
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
            job_agg.c.last_triggered,
            cust_sq.c.customers_count,
            recip_sq.c.recipients_count,
            Cost.price,
            User.first_name,
            User.last_name,
            User.username,
            last_job_sq.c.last_attempted_by,
        )
    )

    rows = []
    for campaign, success_count, failure_count, pending_count, last_triggered, customers_count, recipients_count, price, ufn, uln, uname, last_attempted_by in q.all():
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