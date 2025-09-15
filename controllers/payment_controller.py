# controllers/payment_controller.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Any

from database.db import get_db
from schemas.orders_schema import PaymentCreate, PaymentOut
from services.payment_service import (
    create_payment_link,
    get_payment_by_rzp_id,
    update_payment_status,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/link", response_model=PaymentOut)
def create_link(payload: PaymentCreate, db: Session = Depends(get_db)):
    """
    Create a payment link (real Razorpay if keys exist, mock if not).
    """
    try:
        return create_payment_link(db, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)) -> Any:
    """
    Webhook endpoint for Razorpay (production use).
    Updates payment status when payment_link events occur.
    """
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


@router.get("/mock-pay/{razorpay_id}")
def mock_pay(razorpay_id: str, db: Session = Depends(get_db)):
    """
    Local-only endpoint to simulate payment success.
    Useful if you don’t have Razorpay keys in dev/test.
    """
    payment = get_payment_by_rzp_id(db, razorpay_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Mock payment not found")

    update_payment_status(db, payment, "paid")
    return {"message": f"Payment {razorpay_id} marked as paid (mock)"}
