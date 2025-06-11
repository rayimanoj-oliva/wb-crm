from sqlalchemy.orm import Session
from models.models import Customer
from schemas.CustomerSchema import CustomerCreate


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
def get_customer_by_id(db: Session, customer_id: int) -> Customer:
    return db.query(Customer).filter(Customer.id == customer_id).first()


# List all customers
def get_all_customers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Customer).offset(skip).limit(limit).all()


# Update a customer
def update_customer(db: Session, customer_id: int, updated_data: CustomerCreate) -> Customer:
    customer = get_customer_by_id(db, customer_id)
    if customer:
        customer.wa_id = updated_data.wa_id
        customer.name = updated_data.name
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