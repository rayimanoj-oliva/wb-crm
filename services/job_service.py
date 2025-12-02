from typing import List, Dict, Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session
from uuid import UUID

from sqlalchemy.sql.functions import current_user

from models.models import Campaign, Job, JobStatus, CampaignRecipient


def create_job(db: Session, campaign_id: UUID,current_user) -> Job:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise ValueError("Campaign not found")

    job = Job(campaign_id=campaign.id)
    job.last_attempted_by = current_user.id
    db.add(job)
    db.flush()  # Get job.id before commit

    # Check if campaign has recipients (personalized_recipients)
    # If recipients exist, don't create JobStatus entries for customers
    # Recipients are tracked via CampaignRecipient.status, not JobStatus
    from models.models import CampaignRecipient
    recipients = db.query(CampaignRecipient).filter_by(campaign_id=campaign_id).all()
    
    if not recipients:
        # Only create JobStatus entries if no recipients exist
        # This is for normal CRM campaigns using customers
        statuses = [
            JobStatus(job_id=job.id, customer_id=customer.id, status="pending")
            for customer in campaign.customers
        ]
        if statuses:
            db.add_all(statuses)
    
    db.commit()
    return job

def get_job(db: Session, job_id: UUID) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise ValueError("Job not found")
    return job


def get_jobs_by_campaign_id(db: Session, campaign_id: UUID) -> List[Dict[str, Any]]:
    """
    Get jobs for a campaign with pre-calculated stats.
    OPTIMIZED: Uses aggregation queries instead of loading all statuses.
    Statuses are only loaded when needed (for expansion in UI).
    """
    from models.models import CampaignLog
    from sqlalchemy import func, case

    jobs = db.query(Job).filter(Job.campaign_id == campaign_id).order_by(Job.created_at.desc()).all()

    if not jobs:
        return []

    # Check if campaign uses recipients
    recipient_count = db.query(func.count(CampaignRecipient.id)).filter_by(campaign_id=campaign_id).scalar() or 0
    uses_recipients = recipient_count > 0

    result = []
    for job in jobs:
        job_dict = {
            "id": job.id,
            "campaign_id": job.campaign_id,
            "created_at": job.created_at,
            "last_attempted_by": job.last_attempted_by,
            "last_triggered_time": job.last_triggered_time,
            "statuses": [],
            "stats": {"total": 0, "success": 0, "failure": 0, "pending": 0}
        }

        if uses_recipients:
            # Get stats from CampaignLog using aggregation (fast)
            log_stats = db.query(
                func.count(CampaignLog.id).label("total"),
                func.sum(case((CampaignLog.status == "success", 1), else_=0)).label("success"),
                func.sum(case((CampaignLog.status == "failure", 1), else_=0)).label("failure"),
                func.sum(case((CampaignLog.status.in_(["pending", "queued"]), 1), else_=0)).label("pending")
            ).filter(CampaignLog.campaign_id == campaign_id, CampaignLog.job_id == job.id).first()

            if log_stats and log_stats.total > 0:
                job_dict["stats"] = {
                    "total": log_stats.total or 0,
                    "success": log_stats.success or 0,
                    "failure": log_stats.failure or 0,
                    "pending": log_stats.pending or 0
                }
                # Load only first 100 statuses for display
                logs = db.query(CampaignLog).filter_by(
                    campaign_id=campaign_id, job_id=job.id
                ).limit(100).all()
                for log in logs:
                    status_mapping = {"success": "success", "failure": "failure", "queued": "pending", "pending": "pending"}
                    job_dict["statuses"].append({
                        "target_id": log.target_id,
                        "phone_number": log.phone_number,
                        "status": status_mapping.get(log.status, "pending"),
                        "error_message": log.error_message
                    })
            else:
                # Fallback: Get stats from CampaignRecipient
                rec_stats = db.query(
                    func.count(CampaignRecipient.id).label("total"),
                    func.sum(case((CampaignRecipient.status == "SENT", 1), else_=0)).label("success"),
                    func.sum(case((CampaignRecipient.status == "FAILED", 1), else_=0)).label("failure"),
                    func.sum(case((CampaignRecipient.status.in_(["PENDING", "QUEUED"]), 1), else_=0)).label("pending")
                ).filter(CampaignRecipient.campaign_id == campaign_id).first()

                if rec_stats:
                    job_dict["stats"] = {
                        "total": rec_stats.total or 0,
                        "success": rec_stats.success or 0,
                        "failure": rec_stats.failure or 0,
                        "pending": rec_stats.pending or 0
                    }
                # Load first 100 recipients for display
                recipients = db.query(CampaignRecipient).filter_by(campaign_id=campaign_id).limit(100).all()
                for r in recipients:
                    status_mapping = {"SENT": "success", "FAILED": "failure", "QUEUED": "pending", "PENDING": "pending"}
                    job_dict["statuses"].append({
                        "target_id": r.id,
                        "phone_number": r.phone_number,
                        "status": status_mapping.get(r.status, "pending")
                    })
        else:
            # For normal campaigns using JobStatus
            status_stats = db.query(
                func.count(JobStatus.job_id).label("total"),
                func.sum(case((JobStatus.status == "success", 1), else_=0)).label("success"),
                func.sum(case((JobStatus.status == "failure", 1), else_=0)).label("failure"),
                func.sum(case((JobStatus.status == "pending", 1), else_=0)).label("pending")
            ).filter(JobStatus.job_id == job.id).first()

            if status_stats:
                job_dict["stats"] = {
                    "total": status_stats.total or 0,
                    "success": status_stats.success or 0,
                    "failure": status_stats.failure or 0,
                    "pending": status_stats.pending or 0
                }
            # Load first 100 statuses for display
            for status in job.statuses[:100]:
                status_str = status.status if isinstance(status.status, str) else status.status.value
                job_dict["statuses"].append({
                    "customer_id": status.customer_id,
                    "status": status_str
                })

        result.append(job_dict)

    return result

def get_overall_job_stats(db: Session):
    total = db.query(func.count(JobStatus.job_id)).scalar()

    if total == 0:
        raise ValueError("No jobs found across campaigns.")

    # Correct usage of case in SQLAlchemy
    status_counts = (
        db.query(
            func.sum(case((JobStatus.status == "success", 1), else_=0)).label("success"),
            func.sum(case((JobStatus.status == "failure", 1), else_=0)).label("failure"),
            func.sum(case((JobStatus.status == "pending", 1), else_=0)).label("pending"),
        )
        .one()
    )

    success, failure, pending = status_counts

    return {
        "total_jobs": total,
        "success_percentage": round((success / total) * 100, 2),
        "failure_percentage": round((failure / total) * 100, 2),
        "pending_percentage": round((pending / total) * 100, 2)
    }