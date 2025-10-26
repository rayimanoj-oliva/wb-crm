from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Union
from uuid import UUID
import uuid


class CustomerInfo(BaseModel):
    wa_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class PaymentCreate(BaseModel):
    order_id: Optional[Union[UUID, str]] = None  # can be None for standalone payments, accepts both UUID and string
    amount: float
    currency: str = "INR"
    payment_method: Optional[str] = "upi"
    # Customer contact information for sending payment link (flat, for backward compatibility)
    customer_email: Optional[EmailStr] = None
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
    # Nested customer block (preferred)
    customer: Optional[CustomerInfo] = None
    
    def __init__(self, **data):
        # Convert string order_id to UUID if it's a valid UUID string
        if 'order_id' in data and isinstance(data['order_id'], str):
            try:
                data['order_id'] = uuid.UUID(data['order_id'])
            except ValueError:
                # If it's not a valid UUID, keep it as string
                pass
        super().__init__(**data)
