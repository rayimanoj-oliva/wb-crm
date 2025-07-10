from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from clients.schema import AppointmentQuery, CollectionQuery, SalesQuery
from database.db import get_db
import clients.service as service
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

@router.get("/leads")
def get_leads(db: Session = Depends(get_db)):
    return service.fetch_leads()
