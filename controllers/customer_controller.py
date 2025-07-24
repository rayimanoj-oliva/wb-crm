from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.models import Customer, User
from schemas.customer_schema import CustomerCreate, CustomerOut, CustomerUpdate, AssignUserRequest, CustomerEmailUpdate, \
    CustomerStatusUpdate
from services import customer_service
from database.db import get_db
from uuid import UUID

from services.customer_service import update_customer_status

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

@router.post("/{customer_id}", status_code=200)
def assign_user_to_customer_route(
    customer_id: UUID,
    request: AssignUserRequest,
    db: Session = Depends(get_db)
):
    return customer_service.assign_user_to_customer(db, customer_id, request.user_id)

# GET address by customer ID
@router.get("/{customer_id}/address")
def get_customer_address(customer_id: UUID, db: Session = Depends(get_db)):
    customer = customer_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"address": customer.address}

@router.post("/{customer_id}/address")
def update_customer_address_route(
    customer_id: UUID,
    update_data: CustomerUpdate,  # ✅ Reuse this
    db: Session = Depends(get_db)
):
    if update_data.address is None:
        raise HTTPException(status_code=400, detail="Address is required")

    customer = customer_service.update_customer_address(db, customer_id, update_data.address)
    return {
        "message": "Address updated successfully",
        "customer_id": str(customer.id),
        "address": customer.address
    }

@router.get("/{customer_id}/email")
def get_customer_email(customer_id: UUID, db: Session = Depends(get_db)):
    customer = customer_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"email": customer.email}


@router.post("/{customer_id}/email")
def update_customer_email_route(
    customer_id: UUID,
    update_data: CustomerEmailUpdate,  # ✅ Use the correct schema
    db: Session = Depends(get_db)
):
    customer = customer_service.update_customer_email(db, customer_id, update_data.email)
    return {
        "message": "Email updated successfully",
        "customer_id": str(customer.id),
        "email": customer.email
    }



@router.patch("/customers/{customer_id}/status")
def change_customer_status(customer_id: UUID, update: CustomerStatusUpdate, db: Session = Depends(get_db)):
    updated_customer = update_customer_status(db, customer_id, update.status)
    return {"message": "Customer status updated", "customer_id": str(updated_customer.id), "new_status": updated_customer.customer_status}