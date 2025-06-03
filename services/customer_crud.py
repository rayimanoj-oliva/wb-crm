from sqlalchemy.orm import Session
from models.models import Customer
from schemas.CustomerSchema import CustomerCreate

def create_customer(db: Session, customer: CustomerCreate):
    db_customer = Customer(**customer.dict())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def get_customers(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Customer).offset(skip).limit(limit).all()

def get_customer(db: Session, customer_id):
    return db.query(Customer).filter(Customer.id == customer_id).first()
