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
    Optimized unified conversation list API including:
    - Customers with NO messages
    - Filters that correctly include empty-message customers
    """
    from sqlalchemy import func, and_, or_, desc
    from models.models import Message, FlowLog
    from datetime import datetime
    import re

    # -----------------------------
    # SUBQUERY: latest message per customer
    # -----------------------------
    latest_msg_subq = (
        db.query(
            Message.customer_id,
            Message.body.label("body"),
            Message.timestamp.label("timestamp"),
            Message.from_wa_id.label("from_"),
            Message.to_wa_id.label("to_"),
            Message.sender_type.label("sender_type"),
            func.row_number().over(
                partition_by=Message.customer_id,
                order_by=(Message.timestamp.desc(), Message.id.desc())
            ).label("rn")
        )
        .subquery()
    )

    latest_msg = (
        db.query(
            latest_msg_subq.c.customer_id,
            latest_msg_subq.c.body,
            latest_msg_subq.c.timestamp,
            latest_msg_subq.c.from_,
            latest_msg_subq.c.to_,
            latest_msg_subq.c.sender_type
        )
        .filter(latest_msg_subq.c.rn == 1)
        .subquery()
    )

    # -----------------------------
    # SUBQUERY: latest flow step
    # -----------------------------
    valid_steps = ["entry", "city_selection", "treatment", "concern_list", "last_step"]

    flow_subq = (
        db.query(
            FlowLog.wa_id,
            FlowLog.step,
            FlowLog.description,
            FlowLog.created_at,
            func.row_number().over(
                partition_by=FlowLog.wa_id,
                order_by=FlowLog.created_at.desc()
            ).label("rn")
        )
        .filter(FlowLog.step.in_(valid_steps))
        .subquery()
    )

    flow_latest = (
        db.query(
            flow_subq.c.wa_id,
            flow_subq.c.step,
            flow_subq.c.description,
            flow_subq.c.created_at
        )
        .filter(flow_subq.c.rn == 1)
        .subquery()
    )

    # -----------------------------
    # MAIN QUERY
    # -----------------------------
    query = (
        db.query(
            Customer,
            latest_msg.c.body,
            latest_msg.c.timestamp,
            latest_msg.c.from_,
            latest_msg.c.to_,
            latest_msg.c.sender_type,
            flow_latest.c.step,
            flow_latest.c.description,
            flow_latest.c.created_at
        )
        .outerjoin(latest_msg, Customer.id == latest_msg.c.customer_id)
        .outerjoin(flow_latest, Customer.wa_id == flow_latest.c.wa_id)
    )

    # -----------------------------
    # FILTERS
    # -----------------------------

    # Search filter
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Customer.name.ilike(like),
                Customer.email.ilike(like),
                Customer.wa_id.ilike(like)
            )
        )

    # Assigned agent filter
    if user_id:
        query = query.filter(Customer.user_id == UUID(user_id))

    # Unassigned
    if unassigned_only:
        query = query.filter(Customer.user_id.is_(None))

    # Business number filter (customer must have ANY message with that business number, not just latest)
    if business_number:
        def _build_number_variants(num: str) -> list[str]:
            digits = re.sub(r"\D", "", num or "")
            last10 = digits[-10:] if len(digits) >= 10 else digits
            candidates = {
                num,
                digits,
                last10,
                f"91{last10}" if last10 else None,
                f"+91{last10}" if last10 else None,
                f"+{digits}" if digits else None,
            }
            # Include whatsapp: prefixes
            prefixed = {f"whatsapp:{c}" for c in list(candidates) if c}
            candidates.update(prefixed)
            # Dedupe and drop falsy
            out = []
            seen = set()
            for c in candidates:
                if c and c not in seen:
                    seen.add(c)
                    out.append(c)
            return out

        variants = _build_number_variants(business_number)

        # Restrict to customers who have ANY message (from/to) with the business number
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

    # Date filter (UPDATED to include customers with NO messages)
    if date_filter:
        try:
            target = datetime.strptime(date_filter, "%Y-%m-%d")
            start_dt = datetime.combine(target, datetime.min.time())
            end_dt = datetime.combine(target, datetime.max.time())

            query = query.filter(
                or_(
                    and_(
                        latest_msg.c.timestamp >= start_dt,
                        latest_msg.c.timestamp <= end_dt
                    ),
                    latest_msg.c.timestamp.is_(None)  # <-- keeps customers with NO messages
                )
            )
        except:
            pass

    # Pending reply filter (UPDATED)
    if pending_reply_only:
        query = query.filter(
            or_(
                latest_msg.c.sender_type == "customer",
                latest_msg.c.sender_type.is_(None)  # <-- keeps customers with NO messages
            )
        )

    # -----------------------------
    # ORDER + PAGINATION
    # -----------------------------
    total = query.count()

    query = query.order_by(
        desc(func.coalesce(latest_msg.c.timestamp, Customer.last_message_at, Customer.created_at))
    )

    rows = query.offset(skip).limit(limit).all()

    # -----------------------------
    # UNREAD COUNTS
    # -----------------------------
    unread_map = {r.Customer.wa_id: get_unread_count(r.Customer.wa_id) for r in rows}

    # -----------------------------
    # FORMAT RESPONSE
    # -----------------------------
    items = []
    for r in rows:
        c = r.Customer

        # Determine business number
        business_num = None
        if r.from_ and r.to_:
            business_num = r.to_ if r.from_ == c.wa_id else r.from_

        items.append({
            "id": str(c.id),
            "wa_id": c.wa_id,
            "name": c.name,
            "email": c.email,
            "phone_1": c.phone_1,
            "phone_2": c.phone_2,
            "user_id": str(c.user_id) if c.user_id else None,
            "customer_status": c.customer_status.value if c.customer_status else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,

            # Last message
            "last_message": {
                "body": r.body,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None
            },

            "business_number": business_num,

            "last_step": r.step,
            "step_description": r.description,
            "step_reached_at": r.created_at.isoformat() if r.created_at else None,

            "unread_count": unread_map.get(c.wa_id, 0),
            "is_pending_reply": True if r.sender_type == "customer" else False
        })

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }
