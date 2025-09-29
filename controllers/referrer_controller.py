"""
Referrer tracking controller
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
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


@router.get("/appointments/bookings", response_model=List[ReferrerTrackingResponse])
async def get_appointment_bookings(
    center_name: Optional[str] = Query(None, description="Filter by center name"),
    from_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get all appointment bookings with optional filters"""
    try:
        bookings = referrer_service.get_appointment_bookings(
            db, center_name, from_date, to_date
        )
        return bookings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/appointments/{wa_id}/book", response_model=ReferrerTrackingResponse)
async def book_appointment(
    wa_id: str,
    appointment_date: str = Query(..., description="Appointment date (YYYY-MM-DD)"),
    appointment_time: str = Query(..., description="Appointment time (e.g., 10:30 AM)"),
    treatment_type: str = Query(..., description="Type of treatment"),
    db: Session = Depends(get_db)
):
    """Book an appointment for a WhatsApp user"""
    try:
        updated_referrer = referrer_service.update_appointment_booking(
            db, wa_id, appointment_date, appointment_time, treatment_type
        )
        if not updated_referrer:
            raise HTTPException(status_code=404, detail="Referrer tracking not found")
        return updated_referrer
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
