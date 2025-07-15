from typing import List

from sqlalchemy.orm import Session
from uuid import UUID

from sqlalchemy.sql.functions import current_user

from models.models import Campaign, Job, JobStatus


def create_job(db: Session, campaign_id: UUID,current_user) -> Job:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise ValueError("Campaign not found")

    job = Job(campaign_id=campaign.id)
    job.last_attempted_by = current_user.id
    db.add(job)
    db.flush()  # Get job.id before commit

    statuses = [
        JobStatus(job_id=job.id, customer_id=customer.id, status="pending")
        for customer in campaign.customers
    ]
    db.add_all(statuses)
    db.commit()
    return job

def get_job(db: Session, job_id: UUID) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise ValueError("Job not found")
    return job


def get_jobs_by_campaign_id(db: Session, campaign_id: UUID) -> List[Job]:
    jobs = db.query(Job).filter(Job.campaign_id == campaign_id).all()
    return jobs