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

def get_all_customers(db: Session, skip: int = 0, limit: int = 50, search: str = None,
                       include_flow_step: bool = False, flow_type: str = None):
    """Get all customers with pagination, optional search, and optional flow step data."""
    query = db.query(Customer)

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(search_term)) |
            (Customer.wa_id.ilike(search_term)) |
            (Customer.email.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()

    # Apply ordering and pagination
    customers = query.order_by(Customer.last_message_at.desc().nullslast()).offset(skip).limit(limit).all()

    for customer in customers:
        customer.unread_count = get_unread_count(customer.wa_id)

    # If flow step data is requested, fetch it in a single query
    flow_step_map = {}
    if include_flow_step and customers:
        flow_step_map = get_flow_steps_for_customers(db, [c.wa_id for c in customers], flow_type)

    return {
        "items": customers,
        "total": total,
        "skip": skip,
        "limit": limit,
        "flow_steps": flow_step_map if include_flow_step else None
    }


def get_flow_steps_for_customers(db: Session, wa_ids: list, flow_type: str = None):
    """
    Get last flow step for multiple customers in a single optimized query.
    Returns a dict mapping wa_id -> step data.
    Joins with Customer and Lead tables to get customer name and Zoho lead info.
    """
    from models.models import FlowLog, Lead
    from sqlalchemy import func, and_

    if not wa_ids:
        return {}

    # Normalize flow_type
    normalized_flow_type = flow_type or "lead_appointment"
    if flow_type == "treatment_flow":
        normalized_flow_type = "treatment"
    elif flow_type == "lead_appointment_flow":
        normalized_flow_type = "lead_appointment"

    valid_steps = ["entry", "city_selection", "treatment", "concern_list", "last_step"]

    # Subquery: get max created_at per wa_id for valid steps
    subq = (
        db.query(
            FlowLog.wa_id,
            func.max(FlowLog.created_at).label("max_created_at")
        )
        .filter(
            and_(
                FlowLog.wa_id.in_(wa_ids),
                FlowLog.flow_type == normalized_flow_type,
                FlowLog.step.in_(valid_steps)
            )
        )
        .group_by(FlowLog.wa_id)
        .subquery()
    )

    # Subquery: get latest lead per wa_id (in case of multiple leads)
    lead_subq = (
        db.query(
            Lead.wa_id,
            func.max(Lead.created_at).label("max_lead_created_at")
        )
        .filter(Lead.wa_id.in_(wa_ids))
        .group_by(Lead.wa_id)
        .subquery()
    )

    # Main query: join FlowLog with subquery, Customer table, and Lead table
    results_query = (
        db.query(
            FlowLog,
            Customer.name.label("customer_name"),
            Lead.zoho_lead_id,
            Lead.zoho_mapped_concern,
            Lead.city.label("lead_city"),
            Lead.lead_source
        )
        .join(
            subq,
            and_(
                FlowLog.wa_id == subq.c.wa_id,
                FlowLog.created_at == subq.c.max_created_at
            )
        )
        .outerjoin(Customer, FlowLog.wa_id == Customer.wa_id)
        .outerjoin(
            lead_subq,
            FlowLog.wa_id == lead_subq.c.wa_id
        )
        .outerjoin(
            Lead,
            and_(
                Lead.wa_id == lead_subq.c.wa_id,
                Lead.created_at == lead_subq.c.max_lead_created_at
            )
        )
        .filter(
            and_(
                FlowLog.flow_type == normalized_flow_type,
                FlowLog.step.in_(valid_steps)
            )
        )
        .all()
    )

    # Build results map
    results = {}
    for log, customer_name, zoho_lead_id, zoho_mapped_concern, lead_city, lead_source in results_query:
        results[log.wa_id] = {
            "last_step": log.step,
            "step_name": log.step,
            "reached_at": log.created_at.isoformat() if log.created_at else None,
            "customer_name": customer_name or log.name,
            "description": log.description,
            # Zoho lead info
            "zoho_lead_id": zoho_lead_id,
            "zoho_mapped_concern": zoho_mapped_concern,
            "city": lead_city,
            "lead_source": lead_source,
        }

    return results


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



def get_customers_for_user(db: Session, user_id: UUID, skip: int = 0, limit: int = 50, search: str = None):
    """Get customers for a specific user with pagination and optional search."""
    # Validate that the user exists
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with id {user_id} not found."
        )

    # Build query for customers assigned to this user
    query = db.query(Customer).filter(Customer.user_id == user_id)

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(search_term)) |
            (Customer.wa_id.ilike(search_term)) |
            (Customer.email.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()

    # Fetch customers with pagination
    customers = query.order_by(Customer.last_message_at.desc().nullslast()).offset(skip).limit(limit).all()

    return {"items": customers, "total": total, "skip": skip, "limit": limit}


def update_customer_status(db: Session, customer_id: UUID, new_status: CustomerStatusEnum) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    customer.customer_status = new_status
    db.commit()
    db.refresh(customer)
    return customer


def get_conversations_optimized(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    search: str = None,
    business_number: str = None,
    user_id: str = None,
    unassigned_only: bool = False,
    pending_reply_only: bool = False,
    date_filter: str = None
):
    """
    Optimized unified conversation list API.
    Returns all data needed for the conversations list in a single query.
    """
    from sqlalchemy import func, and_, or_, desc, distinct, case, literal
    from sqlalchemy.orm import aliased
    from models.models import Message, FlowLog, Lead
    from datetime import datetime

    # Known business numbers to exclude from customer results
    business_numbers_set = {'917729992376', '917617613030', '918297882978', '7729992376', '7617613030', '8297882978'}

    # Subquery: Get the latest message for each customer (with row_number to handle ties)
    latest_msg_subq = (
        db.query(
            Message.customer_id,
            Message.body.label("last_message_body"),
            Message.timestamp.label("last_message_timestamp"),
            Message.from_wa_id.label("last_message_from"),
            Message.to_wa_id.label("last_message_to"),
            Message.sender_type.label("last_message_sender_type"),
            func.row_number().over(
                partition_by=Message.customer_id,
                order_by=(Message.timestamp.desc(), Message.id.desc())
            ).label("rn")
        )
        .filter(Message.customer_id.isnot(None))
        .subquery()
    )

    # Filter to get only row number 1 (latest message per customer)
    latest_msg = (
        db.query(
            latest_msg_subq.c.customer_id,
            latest_msg_subq.c.last_message_body,
            latest_msg_subq.c.last_message_timestamp,
            latest_msg_subq.c.last_message_from,
            latest_msg_subq.c.last_message_to,
            latest_msg_subq.c.last_message_sender_type
        )
        .filter(latest_msg_subq.c.rn == 1)
        .subquery()
    )

    # Subquery: Get flow steps (latest per wa_id)
    valid_steps = ["entry", "city_selection", "treatment", "concern_list", "last_step"]
    flow_subq = (
        db.query(
            FlowLog.wa_id,
            FlowLog.step.label("flow_step"),
            FlowLog.description.label("flow_description"),
            FlowLog.created_at.label("flow_reached_at"),
            func.row_number().over(
                partition_by=FlowLog.wa_id,
                order_by=FlowLog.created_at.desc()
            ).label("flow_rn")
        )
        .filter(
            FlowLog.flow_type == "treatment",
            FlowLog.step.in_(valid_steps)
        )
        .subquery()
    )

    flow_latest = (
        db.query(
            flow_subq.c.wa_id,
            flow_subq.c.flow_step,
            flow_subq.c.flow_description,
            flow_subq.c.flow_reached_at
        )
        .filter(flow_subq.c.flow_rn == 1)
        .subquery()
    )

    # Build main query
    query = (
        db.query(
            Customer.id,
            Customer.wa_id,
            Customer.name,
            Customer.email,
            Customer.phone_1,
            Customer.phone_2,
            Customer.user_id,
            Customer.customer_status,
            Customer.last_message_at,
            Customer.created_at,
            # Last message info
            latest_msg.c.last_message_body,
            latest_msg.c.last_message_timestamp,
            latest_msg.c.last_message_from,
            latest_msg.c.last_message_to,
            latest_msg.c.last_message_sender_type,
            # Flow step info
            flow_latest.c.flow_step,
            flow_latest.c.flow_description,
            flow_latest.c.flow_reached_at,
        )
        .outerjoin(latest_msg, Customer.id == latest_msg.c.customer_id)
        .outerjoin(flow_latest, Customer.wa_id == flow_latest.c.wa_id)
    )

    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Customer.name.ilike(search_term),
                Customer.wa_id.ilike(search_term),
                Customer.email.ilike(search_term)
            )
        )

    if user_id:
        from uuid import UUID as PyUUID
        query = query.filter(Customer.user_id == PyUUID(user_id))

    if unassigned_only:
        query = query.filter(Customer.user_id.is_(None))

    # Filter by business number (customer must have ANY message with the number, not just the latest)
    if business_number:
        import re
        from sqlalchemy.sql import exists

        digits = re.sub(r'\D', '', business_number)
        last10 = digits[-10:] if len(digits) >= 10 else digits
        variants = [business_number, digits, last10, f"91{last10}", f"+91{last10}"]
        variants = list(dict.fromkeys(variants))

        # Exists subquery: any message (from/to) matches the business number variants
        msg_exists = (
            db.query(Message.id)
            .filter(
                Message.customer_id == Customer.id,
                or_(
                    Message.from_wa_id.in_(variants),
                    Message.to_wa_id.in_(variants)
                )
            )
            .exists()
        )

        query = query.filter(msg_exists)

    # Filter by date
    if date_filter:
        try:
            target_dt = datetime.strptime(date_filter, '%Y-%m-%d').date()
            start_datetime = datetime.combine(target_dt, datetime.min.time())
            end_datetime = datetime.combine(target_dt, datetime.max.time())
            query = query.filter(
                latest_msg.c.last_message_timestamp >= start_datetime,
                latest_msg.c.last_message_timestamp <= end_datetime
            )
        except ValueError:
            pass

    # Filter pending agent reply (last message was from customer)
    if pending_reply_only:
        query = query.filter(
            latest_msg.c.last_message_sender_type == "customer"
        )

    # Get total count before pagination
    total = query.count()

    # Order by last message timestamp (most recent first)
    query = query.order_by(
        desc(func.coalesce(latest_msg.c.last_message_timestamp, Customer.last_message_at, Customer.created_at))
    )

    # Apply pagination
    results = query.offset(skip).limit(limit).all()

    # Get unread counts from Redis
    wa_ids = [r.wa_id for r in results if r.wa_id]
    unread_map = {}
    for wa_id in wa_ids:
        unread_map[wa_id] = get_unread_count(wa_id)

    # Build response
    items = []
    for r in results:
        # Determine business number from last message
        business_num = None
        if r.last_message_from and r.last_message_to:
            # Business number is the one that's not the customer's wa_id
            if r.last_message_from == r.wa_id:
                business_num = r.last_message_to
            else:
                business_num = r.last_message_from

        # Determine if pending agent reply
        is_pending_reply = r.last_message_sender_type == "customer" if r.last_message_sender_type else False

        items.append({
            "id": str(r.id),
            "wa_id": r.wa_id,
            "name": r.name,
            "email": r.email,
            "phone_1": r.phone_1,
            "phone_2": r.phone_2,
            "user_id": str(r.user_id) if r.user_id else None,
            "customer_status": r.customer_status.value if r.customer_status else None,
            "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            # Last message
            "last_message": {
                "body": r.last_message_body,
                "timestamp": r.last_message_timestamp.isoformat() if r.last_message_timestamp else None
            } if r.last_message_body else None,
            # Business number
            "business_number": business_num,
            # Flow step
            "last_step": r.flow_step,
            "step_description": r.flow_description,
            "step_reached_at": r.flow_reached_at.isoformat() if r.flow_reached_at else None,
            # Unread count
            "unread_count": unread_map.get(r.wa_id, 0),
            # Pending reply status
            "is_pending_reply": is_pending_reply
        })

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }