from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from schemas.CustomerSchema import CustomerCreate, CustomerRead
from services import customer_crud as crud
from uuid import UUID

router = APIRouter()

@router.post("/customers/", response_model=CustomerRead)
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    return crud.create_customer(db, customer)

@router.get("/customers/", response_model=list[CustomerRead])
def list_customers(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_customers(db, skip=skip, limit=limit)

@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: UUID, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
