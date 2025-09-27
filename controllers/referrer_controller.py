"""
Referrer tracking controller
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database.db import get_db
from services.referrer_service import referrer_service
from schemas.referrer_schema import ReferrerTrackingResponse, ReferrerTrackingCreate

router = APIRouter(prefix="/referrer", tags=["referrer"])


@router.post("/track", response_model=ReferrerTrackingResponse)
async def track_referrer(
    referrer_data: ReferrerTrackingCreate,
    db: Session = Depends(get_db)
):
    """Track referrer information for a WhatsApp user"""
    try:
        referrer = referrer_service.create_referrer_tracking(db, referrer_data)
        return referrer
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{wa_id}", response_model=ReferrerTrackingResponse)
async def get_referrer_by_wa_id(
    wa_id: str,
    db: Session = Depends(get_db)
):
    """Get referrer information by WhatsApp ID"""
    referrer = referrer_service.get_referrer_by_wa_id(db, wa_id)
    if not referrer:
        raise HTTPException(status_code=404, detail="Referrer tracking not found")
    return referrer


@router.get("/", response_model=List[ReferrerTrackingResponse])
async def get_all_referrers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all referrer tracking records"""
    from models.models import ReferrerTracking
    referrers = db.query(ReferrerTracking).offset(skip).limit(limit).all()
    return referrers
