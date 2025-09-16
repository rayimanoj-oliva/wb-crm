from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID


class CustomerInfo(BaseModel):
    wa_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class PaymentCreate(BaseModel):
    order_id: Optional[UUID] = None  # can be None for standalone payments
    amount: float
    currency: str = "INR"
    payment_method: Optional[str] = "upi"
    # Customer contact information for sending payment link (flat, for backward compatibility)
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
    # Nested customer block (preferred)
    customer: Optional[CustomerInfo] = None
