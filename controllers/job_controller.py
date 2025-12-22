from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case, or_
from sqlalchemy.orm import Session
from uuid import UUID

from auth import get_current_user
from database.db import get_db
from models.models import JobStatus, Job, CampaignRecipient, WhatsAppAPILog, Campaign
from schemas.job_schemas import JobOut
from services import job_service
import json

router = APIRouter(tags=["Jobs"])

@router.post("/{campaign_id}", response_model=JobOut)
def create_job(campaign_id: UUID, db: Session = Depends(get_db),current_user: dict = Depends(get_current_user)):
    try:
        job = job_service.create_job(db, campaign_id, current_user)
        return job
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return job_service.get_job(db, job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/campaign/{campaign_id}")
def get_jobs_by_campaign_id(campaign_id: UUID, db: Session = Depends(get_db)):
    """
    Get jobs for a campaign. Returns custom format that includes both 
    JobStatus (for customers) and CampaignRecipient statuses (for personalized recipients).
    """
    try:
        return job_service.get_jobs_by_campaign_id(db, campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/campaign/{campaign_id}/job-stats")
def get_campaign_job_stats(campaign_id: UUID, db: Session = Depends(get_db)):
    # Count JobStatus entries (for CRM customers)
    job_status_total = (
        db.query(func.count(JobStatus.job_id))
        .join(Job, Job.id == JobStatus.job_id)
        .filter(Job.campaign_id == campaign_id)
        .scalar() or 0
    )
    
    # Count CampaignRecipient entries (for Excel-uploaded recipients)
    recipient_total = (
        db.query(func.count(CampaignRecipient.id))
        .filter(CampaignRecipient.campaign_id == campaign_id)
        .scalar() or 0
    )
    
    total = job_status_total + recipient_total

    # If no jobs or recipients, return empty stats instead of 404
    if total == 0:
        return {
            "campaign_id": str(campaign_id),
            "total_jobs": 0,
            "success": 0,
            "failure": 0,
            "pending": 0,
            "success_percentage": 0.0,
            "failure_percentage": 0.0,
            "pending_percentage": 0.0
        }

    # Count JobStatus statuses
    job_status_counts = (
        db.query(
            func.count(case((JobStatus.status == "success", 1))).label("success"),
            func.count(case((JobStatus.status == "failure", 1))).label("failure"),
            func.count(case((JobStatus.status == "pending", 1))).label("pending"),
        )
        .join(Job, Job.id == JobStatus.job_id)
        .filter(Job.campaign_id == campaign_id)
        .one()
    )
    js_success, js_failure, js_pending = job_status_counts

    # Count CampaignRecipient statuses (map SENT->success, FAILED->failure, PENDING/QUEUED->pending)
    recipient_status_counts = (
        db.query(
            func.count(case((CampaignRecipient.status == "SENT", 1))).label("success"),
            func.count(case((CampaignRecipient.status == "FAILED", 1))).label("failure"),
            func.count(case((or_(CampaignRecipient.status == "PENDING", CampaignRecipient.status == "QUEUED"), 1))).label("pending"),
        )
        .filter(CampaignRecipient.campaign_id == campaign_id)
        .one()
    )
    rec_success, rec_failure, rec_pending = recipient_status_counts

    # Combine counts
    success = (js_success or 0) + (rec_success or 0)
    failure = (js_failure or 0) + (rec_failure or 0)
    pending = (js_pending or 0) + (rec_pending or 0)

    return {
        "campaign_id": str(campaign_id),
        "total_jobs": total,
        "success": success,
        "failure": failure,
        "pending": pending,
        "success_percentage": round((success / total) * 100, 2) if total > 0 else 0.0,
        "failure_percentage": round((failure / total) * 100, 2) if total > 0 else 0.0,
        "pending_percentage": round((pending / total) * 100, 2) if total > 0 else 0.0
    }

@router.get("/job-stats/overall")
def get_overall_job_stats(db: Session = Depends(get_db)):
    # Total number of job-customer statuses across all campaigns
    total = db.query(func.count(JobStatus.job_id)).scalar()

    if total == 0:
        raise HTTPException(status_code=404, detail="No jobs found across campaigns.")

    # Count each status using conditional aggregation
    status_counts = (
        db.query(
            func.count(case((JobStatus.status == "success", 1))).label("success"),
            func.count(case((JobStatus.status == "failure", 1))).label("failure"),
            func.count(case((JobStatus.status == "pending", 1))).label("pending"),
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

@router.get("/{job_id}/debug-payload")
def debug_job_payload(job_id: UUID, db: Session = Depends(get_db)):
    """Debug endpoint to inspect what payloads were sent for a job"""
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get campaign
        campaign = db.query(Campaign).filter(Campaign.id == job.campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Get API logs for this job
        api_logs = db.query(WhatsAppAPILog).filter(
            WhatsAppAPILog.job_id == job_id
        ).order_by(WhatsAppAPILog.request_time.desc()).limit(10).all()
        
        # Get recipients for this campaign
        recipients = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == job.campaign_id
        ).limit(5).all()
        
        result = {
            "job_id": str(job_id),
            "campaign_id": str(job.campaign_id),
            "campaign_name": campaign.name,
            "campaign_type": campaign.type,
            "campaign_content": campaign.content,
            "recipients_sample": [
                {
                    "id": str(r.id),
                    "phone_number": r.phone_number,
                    "name": r.name,
                    "status": r.status,
                    "params": r.params
                }
                for r in recipients
            ],
            "api_logs": [
                {
                    "id": str(log.id),
                    "phone_number": log.phone_number,
                    "request_time": log.request_time.isoformat() if log.request_time else None,
                    "response_status": log.response_status_code,
                    "error_code": log.error_code,
                    "error_message": log.error_message,
                    "request_payload": log.request_payload,
                    "response_body": log.response_body
                }
                for log in api_logs
            ]
        }
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))