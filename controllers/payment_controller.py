from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Any

from database.db import get_db
from schemas.orders_schema import PaymentCreate, PaymentOut
from services.payment_service import create_payment_link, get_payment_by_rzp_id, update_payment_status


router = APIRouter(tags=["Payments"])


@router.post("/link", response_model=PaymentOut)
def create_link(payload: PaymentCreate, db: Session = Depends(get_db)):
    try:
        return create_payment_link(db, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)) -> Any:
    # Note: In production, validate webhook signature using X-Razorpay-Signature
    body = await request.json()
    event = body.get("event")
    payload = body.get("payload", {})

    if event == "payment_link.paid":
        payment_link = payload.get("payment_link", {}).get("entity", {})
        rzp_id = payment_link.get("id")
        payment = get_payment_by_rzp_id(db, rzp_id)
        if payment:
            update_payment_status(db, payment, "paid")
    elif event == "payment_link.cancelled":
        payment_link = payload.get("payment_link", {}).get("entity", {})
        rzp_id = payment_link.get("id")
        payment = get_payment_by_rzp_id(db, rzp_id)
        if payment:
            update_payment_status(db, payment, "cancelled")

    return {"status": "ok"}


