"""
Payment Controller - API endpoints for payment operations
Handles payment creation, webhooks, and diagnostics
"""

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import os

from database.db import get_db
from models.models import PaymentTransaction, Order
from .schemas import PaymentCreate, PaymentResponse, PaymentDiagnostics, PaymentLinkRequest, PaymentLinkResponse
from .payment_service import PaymentService
from .cart_checkout_service import CartCheckoutService
from .exceptions import PaymentError, RazorpayError, ConfigurationError
from utils.whatsapp import send_message_to_waid

router = APIRouter(tags=["Payments"])

# Razorpay Webhook Secret - Update this with your actual webhook secret from Razorpay dashboard
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "your_razorpay_webhook_secret")


# ---------------- Payment Diagnostics ---------------- #
@router.get("/diagnostics", response_model=PaymentDiagnostics)
async def payment_diagnostics():
    """Diagnose payment system configuration and connectivity"""
    try:
        # Create a temporary database session for diagnostics
        from database.db import SessionLocal
        db = SessionLocal()
        try:
            payment_service = PaymentService(db)
        diagnostics_data = payment_service.get_diagnostics()
        
        # Add webhook configuration check
        diagnostics_data["webhook_config"] = {
            "webhook_secret_configured": bool(RAZORPAY_WEBHOOK_SECRET and RAZORPAY_WEBHOOK_SECRET != "your_razorpay_webhook_secret"),
            "webhook_secret_prefix": RAZORPAY_WEBHOOK_SECRET[:10] + "..." if RAZORPAY_WEBHOOK_SECRET else "Not configured"
        }
        
        return PaymentDiagnostics(**diagnostics_data)
        finally:
            db.close()
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Diagnostics failed: {str(e)}"
        )


# ---------------- Payment Creation ---------------- #
@router.post("/create", response_model=PaymentResponse)
async def create_payment(request: Request, db: Session = Depends(get_db)):
    """Create payment link and save transaction to database"""
    try:
        body = await request.json()
        payload = PaymentCreate(**body)

        # Create payment service instance
        payment_service = PaymentService(db)
        
        # Call service (mock payment for testing)
        payment = payment_service.create_payment_link(payload, mock=True)  # Set to False for live payments

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

        # Derive customer contact (nested preferred, fallback to flat)
        nested_customer = getattr(payload, "customer", None)
        contact_email = getattr(nested_customer, "email", None) if nested_customer else None
        contact_phone = getattr(nested_customer, "phone", None) if nested_customer else None
        contact_name = getattr(nested_customer, "name", None) if nested_customer else None
        contact_wa_id = getattr(nested_customer, "wa_id", None) if nested_customer else None
        contact_email = contact_email or getattr(payload, "customer_email", None)
        contact_phone = contact_phone or getattr(payload, "customer_phone", None)
        contact_name = contact_name or getattr(payload, "customer_name", None)
        # If no explicit wa_id, use phone as wa_id for WhatsApp
        if not contact_wa_id and contact_phone:
            contact_wa_id = contact_phone

        # Optionally send WhatsApp message with payment link if wa_id provided
        if contact_wa_id and payment.razorpay_short_url:
            try:
                await send_message_to_waid(
                    contact_wa_id,
                    f"💳 Please complete your payment of ₹{int(payload.amount)} using this link: {payment.razorpay_short_url}",
                    db,
                )
                # Mark notification as sent when WhatsApp succeeds
                try:
                    payment.notification_sent = True
                    db.commit()
                except Exception:
                    db.rollback()
            except Exception as wa_err:
                print(f"WhatsApp send failed: {wa_err}")

        return PaymentResponse(
            payment_id=str(payment.id),
            razorpay_id=payment.razorpay_id,
            payment_url=payment.razorpay_short_url,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            order_id=payment.order_id,
            created_at=payment.created_at,
            notification_sent=getattr(payment, 'notification_sent', False)
        )

    except PaymentError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Payment creation failed: {e.message}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Payment creation failed: {str(e)}")


# ---------------- Live Payment Creation ---------------- #
@router.post("/create-live", response_model=PaymentResponse)
async def create_live_payment(request: Request, db: Session = Depends(get_db)):
    """Create live payment link using Razorpay API"""
    try:
        body = await request.json()
        payload = PaymentCreate(**body)

        # Create payment service instance
        payment_service = PaymentService(db)
        
        # Call service with live Razorpay API
        payment = payment_service.create_payment_link(payload, mock=False)

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

        # Derive customer contact
        nested_customer = getattr(payload, "customer", None)
        contact_email = getattr(nested_customer, "email", None) if nested_customer else None
        contact_phone = getattr(nested_customer, "phone", None) if nested_customer else None
        contact_name = getattr(nested_customer, "name", None) if nested_customer else None
        contact_wa_id = getattr(nested_customer, "wa_id", None) if nested_customer else None
        contact_email = contact_email or getattr(payload, "customer_email", None)
        contact_phone = contact_phone or getattr(payload, "customer_phone", None)
        contact_name = contact_name or getattr(payload, "customer_name", None)
        if not contact_wa_id and contact_phone:
            contact_wa_id = contact_phone

        # Optionally send WhatsApp message
        if contact_wa_id and payment.razorpay_short_url:
            try:
                await send_message_to_waid(
                    contact_wa_id,
                    f"💳 Please complete your payment of ₹{int(payload.amount)} using this link: {payment.razorpay_short_url}",
                    db,
                )
                try:
                    payment.notification_sent = True
                    db.commit()
                except Exception:
                    db.rollback()
            except Exception as wa_err:
                print(f"WhatsApp send failed: {wa_err}")

        return PaymentResponse(
            payment_id=str(payment.id),
            razorpay_id=payment.razorpay_id,
            payment_url=payment.razorpay_short_url,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            order_id=payment.order_id,
            created_at=payment.created_at,
            notification_sent=getattr(payment, 'notification_sent', False)
        )

    except PaymentError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Live payment creation failed: {e.message}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Live payment creation failed: {str(e)}")


# ---------------- Payment Link for Order ---------------- #
@router.post("/create-link", response_model=PaymentLinkResponse)
async def create_payment_link_for_order(
    request: PaymentLinkRequest, 
    db: Session = Depends(get_db)
):
    """Create payment link for a specific order"""
    try:
        cart_service = CartCheckoutService(db)
        
        result = await cart_service.generate_payment_link_for_order(
            order_id=request.order_id,
            customer_wa_id=request.customer_wa_id,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            customer_phone=request.customer_phone
        )
        
        return PaymentLinkResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment link creation failed: {str(e)}")


# ---------------- Webhook Handling ---------------- #
@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Razorpay webhook and update payment status"""
    try:
        data = await request.body()
        received_signature = request.headers.get("X-Razorpay-Signature")

        print(f"[WEBHOOK] Received webhook - signature header: {received_signature}")
        print(f"[WEBHOOK] Webhook secret configured: {bool(RAZORPAY_WEBHOOK_SECRET and RAZORPAY_WEBHOOK_SECRET != 'your_razorpay_webhook_secret')}")
        
        # Check if signature and secret are present
        if not received_signature:
            print(f"[WEBHOOK] Error: X-Razorpay-Signature header missing")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Razorpay-Signature header missing")
        
        if not RAZORPAY_WEBHOOK_SECRET or RAZORPAY_WEBHOOK_SECRET == "your_razorpay_webhook_secret":
            print(f"[WEBHOOK] Error: RAZORPAY_WEBHOOK_SECRET not configured")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook secret not configured")

        # Validate webhook signature
        payment_service = PaymentService(db)
        signature_valid = payment_service.razorpay_client.validate_webhook_signature(data, received_signature, RAZORPAY_WEBHOOK_SECRET)
        
        if not signature_valid:
            print(f"[WEBHOOK] Error: Signature validation failed")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signature mismatch")

        print(f"[WEBHOOK] Signature validation successful, processing webhook...")

        payload = await request.json()
        gateway_transaction_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")

        payment_transaction = None
        order_updated = False
        customer_notified = False
        
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
                
                # Update associated order status
                try:
                    from models.models import Payment
                    
                    # Find the order associated with this payment
                    payment_record = db.query(Payment).filter(Payment.razorpay_id == gateway_transaction_id).first()
                    if payment_record and payment_record.order_id:
                        order = db.query(Order).filter(Order.id == payment_record.order_id).first()
                        if order:
                            # Update order status
                            order.status = "paid"
                            order.payment_completed_at = datetime.utcnow()
                            
                            # Get customer info for notification
                            customer = order.customer
                            if customer and customer.wa_id:
                                # Send payment confirmation to customer
                                try:
                                    cart_service = CartCheckoutService(db)
                                    order_summary = cart_service.get_order_summary_for_payment(str(order.id))
                                    
                                    confirmation_message = f"""✅ **Payment Successful!**

Your order has been confirmed and payment received.

Order ID: {order.id}
Total Paid: {order_summary.get('formatted_total', 'N/A')}
Items: {order_summary.get('items_count', 0)} items

We'll process your order and send you updates. Thank you for your purchase! 🎉"""
                                    
                                    await send_message_to_waid(customer.wa_id, confirmation_message, db)
                                    customer_notified = True
                                    print(f"[payment_webhook] Payment confirmation sent to customer {customer.wa_id}")
                                except Exception as e:
                                    print(f"[payment_webhook] Failed to send customer notification: {e}")
                            
                            order_updated = True
                            print(f"[payment_webhook] Order {order.id} status updated to paid")
                except Exception as e:
                    print(f"[payment_webhook] Failed to update order status: {e}")
                
                db.commit()

        # Mock Shopify order creation
        shopify_status, shopify_response = payment_service.create_shopify_order(payload)

        print(f"[WEBHOOK] Webhook processed successfully - payment_updated: {payment_transaction is not None}, order_updated: {order_updated}")

        return JSONResponse(
            content={
                "shopify_status": shopify_status,
                "shopify_response": shopify_response,
                "payment_updated": payment_transaction is not None,
                "order_updated": order_updated,
                "customer_notified": customer_notified,
            }
        )

    except HTTPException:
        # Re-raise HTTP exceptions (they're already properly formatted)
        raise
    except Exception as e:
        print(f"[WEBHOOK] Unexpected error processing webhook: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")
