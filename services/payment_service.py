from datetime import datetime
from typing import Optional
import os
import requests
from sqlalchemy.orm import Session
from uuid import uuid4

from models.models import Payment, Order
from schemas.orders_schema import PaymentCreate

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


def _get_auth():
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        return None, None   # 👈 instead of raising
    return key_id, key_secret


def create_payment_link(db: Session, payload: PaymentCreate) -> Payment:
    order: Optional[Order] = db.query(Order).filter(Order.id == payload.order_id).first()
    if not order:
        raise ValueError("Order not found")

    amount_paise = int(round(payload.amount * 100))

    key_id, key_secret = _get_auth()

    if key_id and key_secret:
        # ---- Real Razorpay API call ----
        data = {
            "amount": amount_paise,
            "currency": payload.currency,
            "accept_partial": False,
            "description": f"Payment for order {str(order.id)}",
            "reminder_enable": True,
        }

        resp = requests.post(
            f"{RAZORPAY_BASE_URL}/payment_links",
            auth=(key_id, key_secret),
            json=data,
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Razorpay error: {resp.status_code} {resp.text}")

        r = resp.json()
        razorpay_id = r.get("id")
        short_url = r.get("short_url")
        status = r.get("status", "created")

    else:
        # ---- Mock response for local testing ----
        razorpay_id = f"mock_rzp_{uuid4().hex[:12]}"
        short_url = f"http://localhost:8000/mock-pay/{razorpay_id}"
        status = "created"

    payment = Payment(
        order_id=order.id,
        amount=payload.amount,
        currency=payload.currency,
        razorpay_id=razorpay_id,
        razorpay_short_url=short_url,
        status=status,
        created_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment
