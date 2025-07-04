from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas.customer_schema import CustomerCreate, CustomerOut, CustomerUpdate
from services import customer_service
from database.db import get_db
from uuid import UUID
router = APIRouter(tags=["Customers"])

@router.post("/", response_model=CustomerOut)
def create_or_get_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    return customer_service.get_or_create_customer(db, data)

@router.get("/{customer_id}", response_model=CustomerOut)
def read_customer(customer_id: UUID, db: Session = Depends(get_db)):
    customer = customer_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@router.get("/", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return customer_service.get_all_customers(db)

@router.put("/{customer_id}")
def update_customer(customer_id: UUID, update_data: CustomerUpdate, db: Session = Depends(get_db)):
    return customer_service.update_customer_name(db, customer_id, update_data)