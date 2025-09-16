from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

class PaymentCreate(BaseModel):
    order_id: Optional[UUID] = None  # can be None for standalone payments
    amount: float
    currency: str = "INR"
    payment_method: Optional[str] = "upi"
    # Customer contact information for sending payment link
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
