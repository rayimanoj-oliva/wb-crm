# routers/order.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic.v1 import UUID1
from sqlalchemy.orm import Session
from typing import List
from database.db import get_db
from schemas.OrdersSchema import OrderOut, OrderCreate
from services import order_service

router = APIRouter(tags=["Orders"])

@router.post("/", response_model=OrderOut)
def create_order(order_data: OrderCreate, db: Session = Depends(get_db)):
    return order_service.create_order(db, order_data)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/customer/{customer_id}", response_model=List[OrderOut])
def get_orders_by_customer(customer_id: str, db: Session = Depends(get_db)):
    return order_service.get_orders_by_customer(db, customer_id)