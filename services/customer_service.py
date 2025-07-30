# customer_service.py
from http.client import HTTPException
from typing import List, Tuple # Make sure Tuple is imported
from sqlalchemy.orm import Session
from starlette import status

from cache.redis_connection import redis_client
from models.models import Customer, User # Ensure correct model imports
from schemas.customer_schema import CustomerCreate, CustomerUpdate, CustomerStatusEnum
from uuid import UUID

# This is the ONLY function you need to ensure is updated correctly
def get_or_create_customer(db: Session, customer_data: CustomerCreate) -> Tuple[Customer, bool]:
    """
    Retrieves a customer by wa_id, or creates a new one if not found.
    Returns the customer object and a boolean indicating if the customer was newly created.
    """
    customer = db.query(Customer).filter(Customer.wa_id == customer_data.wa_id).first()

    if customer:
        # Customer exists
        return customer, False # Return the customer object and False (not newly created)
    else:
        # Customer does not exist, create a new one
        new_customer = Customer(wa_id=customer_data.wa_id, name=customer_data.name)
        db.add(new_customer)
        db.commit()
        db.refresh(new_customer)
        return new_customer, True # Return the new customer object and True (newly created)

# Rest of your customer_service.py functions (as you provided them previously)
def get_customer_by_id(db: Session, customer_id: UUID) -> Customer:
    return db.query(Customer).filter(Customer.id == customer_id).first()

def get_unread_count(wa_id: str) -> int:
    count = redis_client.get(f"unread:{wa_id}")
    return int(count) if count else 0

def get_all_customers(db: Session):
    customers = db.query(Customer).order_by(Customer.last_message_at.desc().nullslast()).all()
    for customer in customers:
        customer.unread_count = get_unread_count(customer.wa_id)
    return customers

def update_customer_name(db: Session, customer_id: UUID, update_data: CustomerUpdate):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.name = update_data.name
    db.commit()
    db.refresh(customer)
    return customer

def delete_customer(db: Session, customer_id: int):
    customer = get_customer_by_id(db, customer_id)
    if customer:
        db.delete(customer)
        db.commit()
    return customer

def get_customer_by_wa_id(db: Session, wa_id:str):
    customer = db.query(Customer).filter(Customer.wa_id == wa_id).first()
    if customer: # Added check here
        return customer.id
    return None # Return None if not found

def assign_user_to_customer(db: Session, customer_id: UUID, user_id: UUID | None) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer with id {customer_id} not found.")
    if user_id is None:
        customer.user_id = None
        db.commit()
        db.refresh(customer)
        return customer
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id {user_id} not found.")
    customer.user_id = user.id
    db.commit()
    db.refresh(customer)
    return customer

def update_customer_address(db: Session, customer_id: UUID, address: str) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.address = address
    db.commit()
    db.refresh(customer)
    return customer

def update_customer_email(db: Session, customer_id: UUID, email: str) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.email = email
    db.commit()
    db.refresh(customer)
    return customer

def get_customers_for_user(db: Session, user_id: UUID) -> List[Customer]:
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with id {user_id} not found.")
    customers = db.query(Customer).filter(Customer.user_id == user_id).all()
    return customers

def update_customer_status(db: Session, customer_id: UUID, new_status: CustomerStatusEnum) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    customer.customer_status = new_status
    db.commit()
    db.refresh(customer)
    return customer