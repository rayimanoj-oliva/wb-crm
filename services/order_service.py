# services/order_service.py
from http.client import HTTPException

from pydantic import UUID1

from datetime import datetime, timedelta
from typing import Iterable

from models.models import Order, OrderItem, Payment
from schemas.orders_schema import OrderCreate, OrderItemCreate
from sqlalchemy.orm import Session
import uuid

def create_order(db: Session, order_data: OrderCreate):
    order = Order(
        customer_id=order_data.customer_id,
        catalog_id=order_data.catalog_id,
        timestamp=order_data.timestamp
    )
    db.add(order)
    db.flush()  # Get order.id before adding items

    for item in order_data.items:
        db.add(OrderItem(
            order_id=order.id,
            product_retailer_id=item.product_retailer_id,
            quantity=item.quantity,
            item_price=item.item_price,
            currency=item.currency
        ))

    db.commit()
    db.refresh(order)
    return order


def _is_order_open(db: Session, order: Order) -> bool:
    """Heuristic to decide if an order is still open/modifiable.

    - No successful payment recorded
    - And the order is recent (within last 2 hours)
    """
    try:
        # If any payment exists with a terminal state, consider closed
        terminal_statuses = {"paid", "captured", "authorized", "success", "completed"}
        for p in getattr(order, "payments", []) or []:
            status = (getattr(p, "status", None) or "").lower()
            if status in terminal_statuses:
                return False

        if not getattr(order, "timestamp", None):
            return True

        return (datetime.utcnow() - order.timestamp) <= timedelta(hours=2)
    except Exception:
        # Be permissive if unsure
        return True


def merge_or_create_order(
    db: Session,
    *,
    customer_id,
    catalog_id: str,
    timestamp: datetime,
    items: Iterable[OrderItemCreate],
    is_modification: bool = False,
):
    """Merge items into the latest open order for the customer, or create a new one.

    Args:
        is_modification: If True, marks new items as modification additions
    
    Returns the Order instance used.
    """
    # Find latest order for this customer
    latest_order = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.timestamp.desc())
        .first()
    )

    if latest_order and _is_order_open(db, latest_order):
        print(f"[order_service] DEBUG - Merging {len(list(items))} items into existing order {latest_order.id}")
        print(f"[order_service] DEBUG - Order currently has {len(latest_order.items)} items")
        print(f"[order_service] DEBUG - is_modification: {is_modification}")
        
        # If this is a modification, mark the order as being modified
        if is_modification and not latest_order.modification_started_at:
            latest_order.modification_started_at = timestamp or datetime.utcnow()
            print(f"[order_service] DEBUG - Set modification_started_at: {latest_order.modification_started_at}")
        
        # Append items, update timestamp
        for item in items:
            print(f"[order_service] DEBUG - Adding item: {item.product_retailer_id}, is_modification: {is_modification}")
            db.add(
                OrderItem(
                    order_id=latest_order.id,
                    product_retailer_id=item.product_retailer_id,
                    quantity=item.quantity,
                    item_price=item.item_price,
                    currency=item.currency,
                    is_modification_addition=is_modification,
                    modification_timestamp=timestamp if is_modification else None,
                )
            )
        latest_order.timestamp = timestamp or datetime.utcnow()
        db.commit()
        db.refresh(latest_order)
        print(f"[order_service] DEBUG - After merge, order has {len(latest_order.items)} items")
        
        # Mark as merged for caller logic (ephemeral attribute)
        try:
            setattr(latest_order, "_merged", True)
        except Exception:
            pass
        return latest_order

    # Otherwise create a new order
    print(f"[order_service] DEBUG - Creating new order for customer {customer_id}")
    print(f"[order_service] DEBUG - Latest order exists: {latest_order is not None}")
    if latest_order:
        print(f"[order_service] DEBUG - Latest order is open: {_is_order_open(db, latest_order)}")
    
    created = create_order(
        db,
        OrderCreate(
            customer_id=customer_id,
            catalog_id=catalog_id,
            timestamp=timestamp,
            items=list(items),
        ),
    )
    print(f"[order_service] DEBUG - Created new order {created.id} with {len(created.items)} items")
    
    try:
        setattr(created, "_merged", False)
    except Exception:
        pass
    return created

def get_order(db: Session, order_id: int):
    return db.query(Order).filter(Order.id == order_id).first()


def get_order_items_by_modification_status(db: Session, order_id: str):
    """Get order items separated by modification status.
    
    Returns:
        dict with 'original_items' and 'new_items' lists
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return {"original_items": [], "new_items": []}
    
    original_items = [
        item for item in order.items 
        if not item.is_modification_addition
    ]
    
    new_items = [
        item for item in order.items 
        if item.is_modification_addition
    ]
    
    return {
        "original_items": original_items,
        "new_items": new_items
    }


def get_orders_by_customer(db: Session, customer_id: str):
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise ValueError("Invalid customer UUID")

    orders = db.query(Order).filter(Order.customer_id == customer_uuid).all()
    return orders