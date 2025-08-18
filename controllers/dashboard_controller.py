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

@router.get("/appointments-booked-today")
def appointments_booked_today(center_id: str, db: Session = Depends(get_db)):
    count = get_appointments_booked_today(center_id=center_id, db=db)
    return {"appointments_booked_today": count}

@router.get("/agent-avg-response-time")
def agent_avg_response_time(agent_id: str, center_id: Optional[str] = None, db: Session = Depends(get_db)):

    try:
        avg_time = get_agent_avg_response_time(center_id=center_id, agent_id=agent_id, db=db)
        return {"average_response_time_seconds": avg_time}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while calculating average response time: {e}"
        )

# 🆕 Add Template Status API
@router.get("/template-status")
def template_status(db: Session = Depends(get_db)):
    return get_template_status(db)

# 🆕 Add Recent Failed Messages API
@router.get("/recent-failed-messages")
def recent_failed_messages(db: Session = Depends(get_db)):
    return get_recent_failed_messages(db)