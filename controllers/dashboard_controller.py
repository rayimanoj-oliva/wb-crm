from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import get_db
from services.dashboard_service import get_today_metrics

router = APIRouter(tags=["Dashboard"])

@router.get("/today")
def get_dashboard_today(db: Session = Depends(get_db)):
    return get_today_metrics(db)
