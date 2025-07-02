from http.client import HTTPException

from sqlalchemy.orm import Session

from cache.redis_connection import redis_client
from models.models import Customer
from schemas.customer_schema import CustomerCreate, CustomerUpdate
from uuid import UUID

# Create a new customer or return existing if wa_id matches
def get_or_create_customer(db: Session, customer_data: CustomerCreate) -> Customer:
    customer = db.query(Customer).filter(Customer.wa_id == customer_data.wa_id).first()
    if customer:
        return customer
    new_customer = Customer(wa_id=customer_data.wa_id, name=customer_data.name)
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer


# Get customer by ID
def get_customer_by_id(db: Session, customer_id: UUID) -> Customer:
    return db.query(Customer).filter(Customer.id == customer_id).first()


# List all customers
def get_unread_count(wa_id: str) -> int:
    count = redis_client.get(f"unread:{wa_id}")
    return int(count) if count else 0

def get_all_customers(db: Session, skip: int = 0, limit: int = 100):
    customers = db.query(Customer).offset(skip).all()
    for customer in customers:
        customer.unread_count = get_unread_count(customer.wa_id)  # Inject attribute dynamically
    return customers


def update_customer_name(db: Session, customer_id: UUID, update_data: CustomerUpdate):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.name = update_data.name
    db.commit()
    db.refresh(customer)
    return customer


# Delete a customer
def delete_customer(db: Session, customer_id: int):
    customer = get_customer_by_id(db, customer_id)
    if customer:
        db.delete(customer)
        db.commit()
    return customer

# get customer_id using wa_id
def get_customer_by_wa_id(db: Session, wa_id:str):
    customer = db.query(Customer).filter(Customer.wa_id == wa_id).first()
    return customer.id