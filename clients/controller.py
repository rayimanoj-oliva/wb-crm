from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from clients.schema import AppointmentQuery, CollectionQuery, SalesQuery, Lead , LeadQuery
from database.db import get_db
import clients.service as service
from typing import List
from fastapi import HTTPException
router = APIRouter(tags=["clients"])

@router.get("/appointments")
def get_appointments(query: AppointmentQuery = Depends(), db: Session = Depends(get_db)):
    return service.fetch_appointments(query)

@router.get("/walkins/{appointment_id}")
def get_walkins(appointment_id: str, db: Session = Depends(get_db)):
    return service.fetch_walkins(appointment_id)

@router.get("/collections")
def get_collections(query: CollectionQuery = Depends(), db: Session = Depends(get_db)):
    return service.fetch_collections(query)

@router.get("/sales")
def get_sales(query: SalesQuery = Depends(), db: Session = Depends(get_db)):
    return service.fetch_sales(query)



@router.get("/leads", response_model=List[Lead])
def get_leads(query: LeadQuery = Depends()):
    result = service.fetch_leads(query)

    # Error case
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(
            status_code=result.get("status_code", 500),
            detail=result.get("error")
        )

    # Only return records with at least one contact field
    return [
        lead for lead in result
        if lead.get("Mobile") or lead.get("Phone")
    ]

