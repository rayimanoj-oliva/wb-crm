from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas.CustomerSchema import CustomerCreate, CustomerOut
from services import customer_service
from database.db import get_db

router = APIRouter(tags=["Customers"])

@router.post("/", response_model=CustomerOut)
def create_or_get_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    return customer_service.get_or_create_customer(db, data)

@router.get("/{customer_id}", response_model=CustomerOut)
def read_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = customer_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@router.get("/", response_model=list[CustomerOut])
def list_customers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return customer_service.get_all_customers(db, skip, limit)
