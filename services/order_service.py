# services/order_service.py
from models.models import Order, OrderItem
from schemas.OrdersSchema import OrderCreate
from sqlalchemy.orm import Session

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

def get_order(db: Session, order_id: int):
    return db.query(Order).filter(Order.id == order_id).first()


def get_orders_by_customer(db: Session, customer_id: int):
    return db.query(Order).filter(Order.customer_id == customer_id).all()