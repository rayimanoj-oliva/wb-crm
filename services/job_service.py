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
    """
    jobs = db.query(Job).filter(Job.campaign_id == campaign_id).all()
    
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
            "statuses": []
        }
        
        if uses_recipients:
            # For campaigns with recipients, include recipient statuses
            # Map recipient status to job status format
            for recipient in recipients:
                status_mapping = {
                    "SENT": "success",
                    "FAILED": "failure",
                    "QUEUED": "pending",
                    "PENDING": "pending"
                }
                job_status = status_mapping.get(recipient.status, "pending")
                job_dict["statuses"].append({
                    "customer_id": recipient.id,  # Use recipient.id as identifier
                    "status": job_status
                })
        else:
            # For normal campaigns, include JobStatus entries
            for status in job.statuses:
                job_dict["statuses"].append({
                    "customer_id": status.customer_id,
                    "status": status.status
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