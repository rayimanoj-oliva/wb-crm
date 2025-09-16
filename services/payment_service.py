import os
import requests
from datetime import datetime
from uuid import uuid4
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from models.models import Payment, Order
from schemas.payment_schema import PaymentCreate
from utils.razorpay_utils import create_razorpay_payment_link, get_razorpay_payment_details
from utils.notification_service import send_payment_notifications

# Load env variables
load_dotenv()

# ---- Oliva Razorpay Proxy Config (Fallback) ----
RAZORPAY_TOKEN_URL = "https://payments.olivaclinic.com/api/token"
RAZORPAY_PAYMENT_URL = "https://payments.olivaclinic.com/api/payment"
RAZORPAY_USERNAME = os.getenv("RAZORPAY_USERNAME", "test@example.com")
RAZORPAY_PASSWORD = os.getenv("RAZORPAY_PASSWORD", "123")

# ---- Shopify Config ----
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "oliva-clinic")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "your_api_key")
SHOPIFY_PASSWORD = os.getenv("SHOPIFY_PASSWORD", "your_password")


# ---------------- Razorpay Helpers ---------------- #

def _get_payment_token() -> str:
    """Get Bearer token from Razorpay proxy API."""
    try:
        data = {
            "username": RAZORPAY_USERNAME,
            "password": RAZORPAY_PASSWORD
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        resp = requests.post(RAZORPAY_TOKEN_URL, data=data, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        raise RuntimeError(f"Failed to get Razorpay token: {e}")


def _create_payment_link(token: str, payload: PaymentCreate, order: Order) -> dict:
    """Create Razorpay payment link through Oliva proxy API."""
    try:
        amount_paise = int(round(payload.amount * 100))
        data = {
            "amount": amount_paise,
            "currency": payload.currency,
            "description": f"Payment for order {str(order.id)}",
            "reminder_enable": True,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = requests.post(RAZORPAY_PAYMENT_URL, json=data, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to create Razorpay payment link: {e}")


# ---------------- Main Payment Flow ---------------- #

def create_payment_link(db: Session, payload: PaymentCreate, mock: bool = False) -> Payment:
    """
    Creates payment link using direct Razorpay API or mock for testing.
    Stores Payment in DB.
    """
    if mock:
        # Mock payment for testing
        razorpay_id = f"mock_rzp_{uuid4().hex[:12]}"
        short_url = f"http://localhost:8000/payments/mock-pay/{razorpay_id}"
        status = "created"
    else:
        # Use direct Razorpay API
        try:
            description = f"Payment for order {payload.order_id}" if payload.order_id else "Payment"
            rzp_resp = create_razorpay_payment_link(
                amount=payload.amount,
                currency=payload.currency,
                description=description
            )
            
            if "error" in rzp_resp:
                raise ValueError(f"Razorpay API error: {rzp_resp['error']}")
            
            razorpay_id = rzp_resp.get("id", f"fallback_rzp_{uuid4().hex[:12]}")
            short_url = rzp_resp.get("short_url", f"http://localhost:8000/payments/mock-pay/{razorpay_id}")
            status = rzp_resp.get("status", "created")
            
        except Exception as e:
            print(f"Direct Razorpay API failed, falling back to proxy: {e}")
            # Fallback to proxy method
            order: Optional[Order] = db.query(Order).filter(Order.id == payload.order_id).first() if payload.order_id else None
            if not order and payload.order_id:
                raise ValueError("Order not found")
            
            token = _get_payment_token()
            rzp_resp = _create_payment_link(token, payload, order)
            
            razorpay_id = rzp_resp.get("id", f"fallback_rzp_{uuid4().hex[:12]}")
            short_url = rzp_resp.get("short_url", f"http://localhost:8000/payments/mock-pay/{razorpay_id}")
            status = rzp_resp.get("status", "created")

    payment = Payment(
        order_id=payload.order_id,
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
    
    # Send payment link to customer if contact details are provided
    if payload.customer_email or payload.customer_phone:
        try:
            notification_result = send_payment_notifications(
                payment_link=short_url,
                amount=payload.amount,
                currency=payload.currency,
                customer_email=payload.customer_email,
                customer_phone=payload.customer_phone,
                customer_name=payload.customer_name,
                transaction_id=f"TXN-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
            )
            # Store notification result in payment object for reference
            payment.notification_sent = notification_result.get("overall_success", False)
            db.commit()
        except Exception as e:
            print(f"Failed to send payment notifications: {e}")
            # Don't fail the payment creation if notification fails
            payment.notification_sent = False
            db.commit()
    
    return payment


# ---------------- Shopify Integration ---------------- #

def create_shopify_order(payment_data: dict) -> Tuple[int, dict]:
    """
    Create Shopify order after payment success.
    """
    try:
        customer_info = payment_data.get("personal_info", {})
        address_info = payment_data.get("address_info", {})
        products = payment_data.get("products", [])

        order_data = {
            "order": {
                "line_items": [
                    {
                        "title": p.get("name", "Product"),
                        "price": p.get("price", "0"),
                        "quantity": p.get("quantity", 1),
                    }
                    for p in products
                ],
                "customer": {
                    "first_name": customer_info.get("first_name", "John"),
                    "last_name": customer_info.get("last_name", "Doe"),
                    "email": customer_info.get("email", "john@example.com"),
                },
                "shipping_address": {
                    "first_name": customer_info.get("first_name", "John"),
                    "last_name": customer_info.get("last_name", "Doe"),
                    "address1": address_info.get("address1", "123 Test Street"),
                    "city": address_info.get("city", "Hyderabad"),
                    "province": address_info.get("province", "Telangana"),
                    "country": address_info.get("country", "India"),
                    "zip": address_info.get("zip", "500001"),
                    "phone": customer_info.get("phone", "1234567890"),
                },
                "financial_status": "paid",
                "inventory_behaviour": "bypass",
                "send_receipt": True,
                "send_fulfillment_receipt": True,
            }
        }

        shopify_url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}.myshopify.com/admin/api/2024-04/orders.json"
        headers = {"Content-Type": "application/json"}
        resp = requests.post(shopify_url, json=order_data, headers=headers, timeout=20)

        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {"error": str(e)}


# ---------------- DB Utility ---------------- #

def get_payment_by_id(db: Session, payment_id):
    return db.query(Payment).filter(Payment.id == payment_id).first()


def get_payment_by_rzp_id(db: Session, rzp_id: str):
    return db.query(Payment).filter(Payment.razorpay_id == rzp_id).first()


def update_payment_status(db: Session, payment: Payment, status: str) -> Payment:
    payment.status = status
    payment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(payment)
    return payment
