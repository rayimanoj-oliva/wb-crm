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
):
    """Merge items into the latest open order for the customer, or create a new one.

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
        # Append items, update timestamp
        for item in items:
            db.add(
                OrderItem(
                    order_id=latest_order.id,
                    product_retailer_id=item.product_retailer_id,
                    quantity=item.quantity,
                    item_price=item.item_price,
                    currency=item.currency,
                )
            )
        latest_order.timestamp = timestamp or datetime.utcnow()
        db.commit()
        db.refresh(latest_order)
        return latest_order

    # Otherwise create a new order
    return create_order(
        db,
        OrderCreate(
            customer_id=customer_id,
            catalog_id=catalog_id,
            timestamp=timestamp,
            items=list(items),
        ),
    )

def get_order(db: Session, order_id: int):
    return db.query(Order).filter(Order.id == order_id).first()


def get_orders_by_customer(db: Session, customer_id: str):
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise ValueError("Invalid customer UUID")

    orders = db.query(Order).filter(Order.customer_id == customer_uuid).all()
    return orders