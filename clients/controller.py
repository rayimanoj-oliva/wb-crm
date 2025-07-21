# clients/controller.py

from fastapi import APIRouter, Query, HTTPException
from typing import List
from clients.schema import WalkinAppointment
from clients.service import get_walkin_appointments_by_date
from datetime import datetime

router = APIRouter()

@router.get("/walkin/by-date", response_model=List[WalkinAppointment])
async def get_walkin_by_date(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD")
):
    # Validation
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="from_date cannot be after to_date")

    try:
        data = get_walkin_appointments_by_date(from_date, to_date)
        if not data:
            raise HTTPException(status_code=404, detail="No appointments found for the given dates")
        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
