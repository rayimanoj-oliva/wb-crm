from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from database.db import get_db
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