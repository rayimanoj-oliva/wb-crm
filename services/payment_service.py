from datetime import datetime
from typing import Optional

import os
import requests
from sqlalchemy.orm import Session

from models.models import Payment, Order
from schemas.orders_schema import PaymentCreate


RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


def _get_auth():
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError("Missing RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET in environment")
    return key_id, key_secret


def create_payment_link(db: Session, payload: PaymentCreate) -> Payment:
    order: Optional[Order] = db.query(Order).filter(Order.id == payload.order_id).first()
    if not order:
        raise ValueError("Order not found")

    amount_paise = int(round(payload.amount * 100))

    data = {
        "amount": amount_paise,
        "currency": payload.currency,
        "accept_partial": False,
        "description": f"Payment for order {str(order.id)}",
        "reminder_enable": True,
    }

    key_id, key_secret = _get_auth()
    resp = requests.post(
        f"{RAZORPAY_BASE_URL}/payment_links",
        auth=(key_id, key_secret),
        json=data,
        timeout=20,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Razorpay error: {resp.status_code} {resp.text}")

    r = resp.json()
    payment = Payment(
        order_id=order.id,
        amount=payload.amount,
        currency=payload.currency,
        razorpay_id=r.get("id"),
        razorpay_short_url=r.get("short_url"),
        status=r.get("status", "created"),
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def get_payment_by_id(db: Session, payment_id):
    return db.query(Payment).filter(Payment.id == payment_id).first()


def get_payment_by_rzp_id(db: Session, rzp_id: str):
    return db.query(Payment).filter(Payment.razorpay_id == rzp_id).first()


def update_payment_status(db: Session, payment: Payment, status: str):
    payment.status = status
    db.commit()
    db.refresh(payment)
    return payment


