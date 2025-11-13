from http.client import HTTPException
from idlelib.query import Query
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import get_db
from services.dashboard_service import get_today_metrics, get_total_customers, get_agent_avg_response_time
from services.dashboard_service import get_appointments_booked_today
from services.dashboard_service import (
    get_template_status,
    get_recent_failed_messages
)
router = APIRouter(tags=["Dashboard"])

@router.get("/today")
def get_dashboard_today(db: Session = Depends(get_db)):
    return get_today_metrics(db)
@router.get("/total-customers")
def total_customers(db: Session = Depends(get_db)):
    count = get_total_customers(db)
    return {"total_customers": count}

@router.get("/appointments-today")
def appointments_booked_today(center_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get count of appointments booked today from treatment flow.
    center_id is optional - if not provided, returns count for all centers.
    """
    count = get_appointments_booked_today(center_id=center_id, db=db)
    return {"count": count, "percentage": 0}  # percentage can be calculated separately if needed

# 🆕 Add Template Status API
@router.get("/template-status")
def template_status(db: Session = Depends(get_db)):
    return get_template_status(db)

# Breakdown endpoints for individual template status counts
@router.get("/template-status/approved")
def template_status_approved(db: Session = Depends(get_db)):
    stats = get_template_status(db)
    return {"count": stats.get("approved", 0)}

@router.get("/template-status/failed")
def template_status_failed(db: Session = Depends(get_db)):
    stats = get_template_status(db)
    # "failed" maps to rejected templates in current schema
    return {"count": stats.get("failed", 0)}

@router.get("/template-status/review")
def template_status_review(db: Session = Depends(get_db)):
    stats = get_template_status(db)
    # "review" maps to pending in current schema
    return {"count": stats.get("pending", 0)}

# 🆕 Add Recent Failed Messages API
@router.get("/recent-failed-messages")
def recent_failed_messages(db: Session = Depends(get_db)):
    return get_recent_failed_messages(db)