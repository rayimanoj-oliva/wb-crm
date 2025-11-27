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
    Get jobs for a campaign, including statuses from both JobStatus (customers)
    and CampaignRecipient (personalized recipients).

    FIXED: Now correctly associates recipients with specific jobs using CampaignLog
    instead of showing all recipients for every job.
    """
    from models.models import CampaignLog

    jobs = db.query(Job).filter(Job.campaign_id == campaign_id).order_by(Job.created_at.desc()).all()

    # Check if campaign uses recipients
    recipients = db.query(CampaignRecipient).filter_by(campaign_id=campaign_id).all()
    uses_recipients = len(recipients) > 0

    result = []
    for job in jobs:
        job_dict = {
            "id": job.id,
            "campaign_id": job.campaign_id,
            "created_at": job.created_at,
            "last_attempted_by": job.last_attempted_by,
            "last_triggered_time": job.last_triggered_time,
            "statuses": [],
            "stats": {
                "total": 0,
                "success": 0,
                "failure": 0,
                "pending": 0
            }
        }

        if uses_recipients:
            # FIXED: Get statuses from CampaignLog for this specific job
            logs = db.query(CampaignLog).filter_by(
                campaign_id=campaign_id,
                job_id=job.id
            ).all()

            if logs:
                # Use logs to get accurate per-job status
                for log in logs:
                    status_mapping = {
                        "success": "success",
                        "failure": "failure",
                        "queued": "pending",
                        "pending": "pending"
                    }
                    mapped_status = status_mapping.get(log.status, "pending")
                    job_dict["statuses"].append({
                        "target_id": log.target_id,
                        "phone_number": log.phone_number,
                        "status": mapped_status,
                        "error_message": log.error_message
                    })
                    job_dict["stats"]["total"] += 1
                    job_dict["stats"][mapped_status] += 1
            else:
                # Fallback: If no logs yet, show recipients with their current status
                # This handles the case where campaign just started
                for recipient in recipients:
                    status_mapping = {
                        "SENT": "success",
                        "FAILED": "failure",
                        "QUEUED": "pending",
                        "PENDING": "pending"
                    }
                    job_status = status_mapping.get(recipient.status, "pending")
                    job_dict["statuses"].append({
                        "target_id": recipient.id,
                        "phone_number": recipient.phone_number,
                        "status": job_status
                    })
                    job_dict["stats"]["total"] += 1
                    job_dict["stats"][job_status] += 1
        else:
            # For normal campaigns, include JobStatus entries
            for status in job.statuses:
                status_str = status.status if isinstance(status.status, str) else status.status.value
                job_dict["statuses"].append({
                    "customer_id": status.customer_id,
                    "status": status_str
                })
                job_dict["stats"]["total"] += 1
                job_dict["stats"][status_str] += 1

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