from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import os

from database.db import get_db
from models.models import PaymentTransaction, Order
from schemas.payment_schema import PaymentCreate
from services.payment_service import create_payment_link, create_shopify_order
from utils.razorpay_utils import validate_razorpay_signature

router = APIRouter(prefix="/payments", tags=["Payments"])

# Razorpay Webhook Secret - Update this with your actual webhook secret from Razorpay dashboard
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "your_razorpay_webhook_secret")


# ---------------- Payment Creation ---------------- #
@router.post("/create")
async def create_payment(request: Request, db: Session = Depends(get_db)):
    """Create mock payment link and save transaction to database"""
    try:
        body = await request.json()
        payload = PaymentCreate(**body)

        # Call service (mock payment for testing)
        payment = create_payment_link(db, payload, mock=True)  # Set to False for live payments

        # Generate unique transaction ID
        transaction_id = f"TXN-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # Save payment transaction
        payment_transaction = PaymentTransaction(
            transaction_id=transaction_id,
            payment_method=payload.payment_method or "upi",
            payment_gateway="razorpay",
            amount=payload.amount,
            currency=payload.currency,
            status=payment.status,
            gateway_response={"id": payment.razorpay_id, "short_url": payment.razorpay_short_url},
            gateway_transaction_id=payment.razorpay_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(payment_transaction)
        db.commit()
        db.refresh(payment_transaction)

        return JSONResponse(
            content={
                "transaction_id": transaction_id,
                "payment_link": payment.razorpay_short_url,
                "razorpay_id": payment.razorpay_id,
                "status": payment.status,
                "mock_payment": True,
                "notification_sent": getattr(payment, 'notification_sent', False),
                "customer_contact": {
                    "email": payload.customer_email,
                    "phone": payload.customer_phone,
                    "name": payload.customer_name
                }
            }
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Payment creation failed: {str(e)}")


# ---------------- Live Payment Creation ---------------- #
@router.post("/create-live")
async def create_live_payment(request: Request, db: Session = Depends(get_db)):
    """Create live payment link using Razorpay API"""
    try:
        body = await request.json()
        payload = PaymentCreate(**body)

        # Call service with live Razorpay API
        payment = create_payment_link(db, payload, mock=False)

        # Generate unique transaction ID
        transaction_id = f"TXN-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # Save payment transaction
        payment_transaction = PaymentTransaction(
            transaction_id=transaction_id,
            payment_method=payload.payment_method or "upi",
            payment_gateway="razorpay",
            amount=payload.amount,
            currency=payload.currency,
            status=payment.status,
            gateway_response={"id": payment.razorpay_id, "short_url": payment.razorpay_short_url},
            gateway_transaction_id=payment.razorpay_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(payment_transaction)
        db.commit()
        db.refresh(payment_transaction)

        return JSONResponse(
            content={
                "transaction_id": transaction_id,
                "payment_link": payment.razorpay_short_url,
                "razorpay_id": payment.razorpay_id,
                "status": payment.status,
                "live_payment": True,
                "notification_sent": getattr(payment, 'notification_sent', False),
                "customer_contact": {
                    "email": payload.customer_email,
                    "phone": payload.customer_phone,
                    "name": payload.customer_name
                }
            }
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Live payment creation failed: {str(e)}")


# ---------------- Webhook Handling ---------------- #
@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Razorpay webhook and update payment status"""
    try:
        data = await request.body()
        received_signature = request.headers.get("X-Razorpay-Signature")

        if not validate_razorpay_signature(data, received_signature, RAZORPAY_WEBHOOK_SECRET):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signature mismatch")

        payload = await request.json()
        gateway_transaction_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")

        payment_transaction = None
        if gateway_transaction_id:
            payment_transaction = (
                db.query(PaymentTransaction)
                .filter(PaymentTransaction.gateway_transaction_id == gateway_transaction_id)
                .first()
            )
            if payment_transaction:
                payment_transaction.status = "paid"
                payment_transaction.gateway_response = payload
                payment_transaction.updated_at = datetime.utcnow()
                db.commit()

        # Mock Shopify order creation
        shopify_status, shopify_response = create_shopify_order(payload, mock=True)

        return JSONResponse(
            content={
                "shopify_status": shopify_status,
                "shopify_response": shopify_response,
                "payment_updated": payment_transaction is not None,
            }
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")
