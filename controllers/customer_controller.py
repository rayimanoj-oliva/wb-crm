from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models.models import Customer, User
from schemas.customer_schema import CustomerCreate, CustomerOut, CustomerUpdate, AssignUserRequest, CustomerEmailUpdate, \
    CustomerStatusUpdate
from services import customer_service
from database.db import get_db
from uuid import UUID

from services.customer_service import update_customer_status

router = APIRouter(tags=["Customers"])


@router.get("/conversations")
def list_conversations_optimized(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    business_number: Optional[str] = Query(None, description="Filter by business number"),
    user_id: Optional[str] = Query(None, description="Filter by assigned user ID"),
    unassigned_only: bool = Query(False, description="Show only unassigned customers"),
    pending_reply_only: bool = Query(False, description="Show only customers pending agent reply"),
    date_filter: Optional[str] = Query(None, description="Filter by message date (YYYY-MM-DD)"),
    unread_only: bool = Query(False, description="Show only customers with unread messages"),
    db: Session = Depends(get_db)
):
    """
    Optimized unified conversation list API.

    Returns customers with:
    - Last message info (body, timestamp, business_number)
    - Flow step data
    - Pending reply status
    - Unread counts

    All in a single API call to replace multiple frontend calls.
    """
    return customer_service.get_conversations_optimized(
        db,
        skip=skip,
        limit=limit,
        search=search,
        business_number=business_number,
        user_id=user_id,
        unassigned_only=unassigned_only,
        pending_reply_only=pending_reply_only,
        date_filter=date_filter,
        unread_only=unread_only,
    )

@router.get("/conversations/by-peer")
def list_conversations_by_peer(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    business_number: Optional[str] = Query(None, description="Filter by business number (peer)"),
    user_id: Optional[str] = Query(None, description="Filter by assigned user ID"),
    unassigned_only: bool = Query(False, description="Show only unassigned customers"),
    pending_reply_only: bool = Query(False, description="Show only customers pending agent reply"),
    date_filter: Optional[str] = Query(None, description="Filter by message date (YYYY-MM-DD)"),
    unread_only: bool = Query(False, description="Show only conversations with unread messages"),
    db: Session = Depends(get_db)
):
    """
    Returns conversations grouped by (customer_id, peer_number).
    Use when you need the same customer to appear under multiple business numbers they've chatted with.
    """
    return customer_service.get_conversations_by_peer(
        db,
        skip=skip,
        limit=limit,
        search=search,
        business_number=business_number,
        user_id=user_id,
        unassigned_only=unassigned_only,
        pending_reply_only=pending_reply_only,
        date_filter=date_filter,
        unread_only=unread_only,
    )

@router.post("/", response_model=CustomerOut)
def create_or_get_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    return customer_service.get_or_create_customer(db, data)

@router.get("/{customer_id}", response_model=CustomerOut)
def read_customer(customer_id: UUID, db: Session = Depends(get_db)):
    customer = customer_service.get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@router.get("/")
def list_customers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    include_flow_step: bool = Query(False, description="Include last flow step data for each customer"),
    flow_type: Optional[str] = Query(None, description="Flow type: treatment or lead_appointment"),
    db: Session = Depends(get_db)
):
    """
    List customers with pagination and optional search.

    Use include_flow_step=true to get flow step data in a single API call:
    GET /customer/?include_flow_step=true&flow_type=treatment

    Response includes:
    - items: list of customers
    - flow_steps: dict mapping wa_id -> {last_step, reached_at, ...}
    """
    return customer_service.get_all_customers(
        db, skip=skip, limit=limit, search=search,
        include_flow_step=include_flow_step, flow_type=flow_type
    )

@router.put("/{customer_id}")
def update_customer(customer_id: UUID, update_data: CustomerUpdate, db: Session = Depends(get_db)):
    return customer_service.update_customer(db, customer_id, update_data)

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