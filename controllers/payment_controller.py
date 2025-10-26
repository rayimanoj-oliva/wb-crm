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
from utils.whatsapp import send_message_to_waid

router = APIRouter(tags=["Payments"])

# Razorpay Webhook Secret - Update this with your actual webhook secret from Razorpay dashboard
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "your_razorpay_webhook_secret")


# ---------------- Payment Diagnostics ---------------- #
@router.get("/diagnostics")
async def payment_diagnostics():
    """Diagnose payment system configuration and connectivity"""
    try:
        import os
        from utils.razorpay_utils import RAZORPAY_KEY_ID, RAZORPAY_SECRET, RAZORPAY_BASE_URL
        
        diagnostics = {
            "razorpay_config": {
                "key_id_configured": bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_ID != "rzp_test_123456789"),
                "secret_configured": bool(RAZORPAY_SECRET and RAZORPAY_SECRET != "test_secret_123456789"),
                "base_url": RAZORPAY_BASE_URL,
                "key_id_prefix": RAZORPAY_KEY_ID[:8] + "..." if RAZORPAY_KEY_ID else "Not configured"
            },
            "environment": {
                "razorpay_username": bool(os.getenv("RAZORPAY_USERNAME")),
                "razorpay_password": bool(os.getenv("RAZORPAY_PASSWORD")),
                "proxy_token_url": os.getenv("RAZORPAY_TOKEN_URL", "Not configured"),
                "proxy_payment_url": os.getenv("RAZORPAY_PAYMENT_URL", "Not configured")
            }
        }
        
        # Test Razorpay API connectivity
        try:
            from utils.razorpay_utils import create_razorpay_payment_link
            test_response = create_razorpay_payment_link(amount=1.0, description="Test payment")
            
            if "error" in test_response:
                diagnostics["api_test"] = {
                    "status": "failed",
                    "error": test_response.get("error"),
                    "error_type": test_response.get("error_type")
                }
            else:
                diagnostics["api_test"] = {
                    "status": "success",
                    "payment_id": test_response.get("id", "Unknown")
                }
        except Exception as e:
            diagnostics["api_test"] = {
                "status": "exception",
                "error": str(e)
            }
        
        return JSONResponse(content=diagnostics)
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Diagnostics failed: {str(e)}"},
            status_code=500
        )


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

        return JSONResponse(
            content={
                "transaction_id": transaction_id,
                "payment_link": payment.razorpay_short_url,
                "razorpay_id": payment.razorpay_id,
                "status": payment.status,
                "mock_payment": True,
                "notification_sent": getattr(payment, 'notification_sent', False),
                "customer_contact": {
                    "email": contact_email,
                    "phone": contact_phone,
                    "name": contact_name,
                    "wa_id": contact_wa_id,
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

        return JSONResponse(
            content={
                "transaction_id": transaction_id,
                "payment_link": payment.razorpay_short_url,
                "razorpay_id": payment.razorpay_id,
                "status": payment.status,
                "live_payment": True,
                "notification_sent": getattr(payment, 'notification_sent', False),
                "customer_contact": {
                    "email": contact_email,
                    "phone": contact_phone,
                    "name": contact_name,
                    "wa_id": contact_wa_id,
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
                    from models.models import Order, Payment
                    from utils.whatsapp import send_message_to_waid
                    
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
                                    from services.cart_checkout_service import CartCheckoutService
                                    checkout_service = CartCheckoutService(db)
                                    order_summary = checkout_service.get_order_summary_for_payment(str(order.id))
                                    
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
        shopify_status, shopify_response = create_shopify_order(payload, mock=True)

        return JSONResponse(
            content={
                "shopify_status": shopify_status,
                "shopify_response": shopify_response,
                "payment_updated": payment_transaction is not None,
                "order_updated": order_updated,
                "customer_notified": customer_notified,
            }
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")
