from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from uuid import UUID

from database.db import get_db
from models.models import JobStatus, Job
from schemas.job_schemas import JobOut
from services import job_service

router = APIRouter(tags=["Jobs"])

@router.post("/{campaign_id}", response_model=JobOut)
def create_job(campaign_id: UUID, db: Session = Depends(get_db)):
    try:
        job = job_service.create_job(db, campaign_id)
        return job
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return job_service.get_job(db, job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/campaign/{campaign_id}", response_model=List[JobOut])
def get_jobs_by_campaign_id(campaign_id: UUID, db: Session = Depends(get_db)):
    try:
        return job_service.get_jobs_by_campaign_id(db, campaign_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/campaign/{campaign_id}/job-stats")
def get_campaign_job_stats(campaign_id: UUID, db: Session = Depends(get_db)):
    # Fetch total number of job-customer statuses for the campaign
    total_query = (
        db.query(func.count(JobStatus.job_id))
        .join(Job, Job.id == JobStatus.job_id)
        .filter(Job.campaign_id == campaign_id)
    )
    total = total_query.scalar()

    if total == 0:
        raise HTTPException(status_code=404, detail="No jobs found for this campaign.")

    # Count each status using conditional aggregation
    status_counts = (
        db.query(
            func.count(case((JobStatus.status == "success", 1))).label("success"),
            func.count(case((JobStatus.status == "failure", 1))).label("failure"),
            func.count(case((JobStatus.status == "pending", 1))).label("pending"),
        )
        .join(Job, Job.id == JobStatus.job_id)
        .filter(Job.campaign_id == campaign_id)
        .one()
    )

    success, failure, pending = status_counts

    return {
        "campaign_id": campaign_id,
        "total_jobs": total,
        "success_percentage": round((success / total) * 100, 2),
        "failure_percentage": round((failure / total) * 100, 2),
        "pending_percentage": round((pending / total) * 100, 2)
    }