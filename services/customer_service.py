from http.client import HTTPException
from typing import List

from sqlalchemy.orm import Session
from starlette import status

from cache.redis_connection import get_redis_client
from models.models import Customer, User
from schemas.customer_schema import CustomerCreate, CustomerUpdate, CustomerStatusEnum
from uuid import UUID

# Create a new customer or return existing if wa_id matches
def get_or_create_customer(db: Session, customer_data: CustomerCreate) -> Customer:
    customer = db.query(Customer).filter(Customer.wa_id == customer_data.wa_id).first()
    if customer:
        # Ensure default phone_1 is set from wa_id if missing
        if not getattr(customer, "phone_1", None):
            try:
                import re as _re
                wa_digits = _re.sub(r"\D", "", customer_data.wa_id or "")
                wa_last10 = wa_digits[-10:] if len(wa_digits) >= 10 else wa_digits
                customer.phone_1 = ("+91" + wa_last10) if len(wa_last10) == 10 else (customer_data.wa_id or None)
                db.commit()
                db.refresh(customer)
            except Exception:
                pass
        return customer
    # Derive phone_1 from wa_id by default if not provided
    try:
        import re as _re
        wa_digits_new = _re.sub(r"\D", "", customer_data.wa_id or "")
        wa_last10_new = wa_digits_new[-10:] if len(wa_digits_new) >= 10 else wa_digits_new
        default_phone_1 = ("+91" + wa_last10_new) if len(wa_last10_new) == 10 else (customer_data.wa_id or None)
    except Exception:
        default_phone_1 = customer_data.wa_id
    new_customer = Customer(
        wa_id=customer_data.wa_id,
        name=customer_data.name,
        phone_1=customer_data.phone_1 or default_phone_1,
        phone_2=customer_data.phone_2,
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer


# Get customer by ID
def get_customer_by_id(db: Session, customer_id: UUID) -> Customer:
    return db.query(Customer).filter(Customer.id == customer_id).first()


# List all customers
def get_unread_count(wa_id: str) -> int:
    redis_client = get_redis_client()
    if not redis_client:
        return 0
    try:
        count = redis_client.get(f"unread:{wa_id}")
        return int(count) if count else 0
    except Exception:
        return 0

def get_all_customers(db: Session):
    customers = db.query(Customer).order_by(Customer.last_message_at.desc().nullslast()).all()
    for customer in customers:
        customer.unread_count = get_unread_count(customer.wa_id)  # Inject attribute dynamically
    return customers


def update_customer(db: Session, customer_id: UUID, update_data: CustomerUpdate):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if update_data.name is not None:
        customer.name = update_data.name
    if hasattr(update_data, "phone_1") and update_data.phone_1 is not None:
        customer.phone_1 = update_data.phone_1
    if hasattr(update_data, "phone_2") and update_data.phone_2 is not None:
        customer.phone_2 = update_data.phone_2
    if hasattr(update_data, "address") and update_data.address is not None:
        customer.address = update_data.address
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

# Get full customer record by wa_id
def get_customer_record_by_wa_id(db: Session, wa_id: str) -> Customer | None:
    return db.query(Customer).filter(Customer.wa_id == wa_id).first()

def assign_user_to_customer(db: Session, customer_id: UUID, user_id: UUID | None) -> Customer:
    # 1. Get the customer
    customer = db.query(Customer).filter(Customer.id == customer_id).one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with id {customer_id} not found."
        )

    # 2. Unassign user if user_id is None
    if user_id is None:
        customer.user_id = None
        db.commit()
        db.refresh(customer)
        return customer

    # 3. Get the user
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found."
        )

    # 4. Assign user to customer
    customer.user_id = user.id
    db.commit()
    db.refresh(customer)

    return customer
    #5. Update customer address
def update_customer_address(db: Session, customer_id: UUID, address: str) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.address = address
    db.commit()
    db.refresh(customer)
    return customer
    #6. Update customer email


def update_customer_email(db: Session, customer_id: UUID, email: str) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.email = email
    db.commit()
    db.refresh(customer)
    return customer



def get_customers_for_user(db: Session, user_id: UUID) -> List[Customer]:
    # Optional: Validate that the user exists
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with id {user_id} not found."
        )

    # Fetch all customers assigned to this user
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