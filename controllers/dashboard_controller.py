from idlelib.query import Query

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import get_db
from services.dashboard_service import get_today_metrics, get_total_customers
from services.dashboard_service import get_appointments_booked_today

router = APIRouter(tags=["Dashboard"])

@router.get("/today")
def get_dashboard_today(db: Session = Depends(get_db)):
    return get_today_metrics(db)
@router.get("/total-customers")
def total_customers(db: Session = Depends(get_db)):
    count = get_total_customers(db)
    return {"total_customers": count}

@router.get("/dashboard/appointments-booked-today")
def appointments_booked_today(center_id: str, db: Session = Depends(get_db)):
    count = get_appointments_booked_today(center_id=center_id, db=db)
    return {"appointments_booked_today": count}