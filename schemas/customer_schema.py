from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

from models.models import CustomerStatusEnum


# Schema for creating a customer
class CustomerCreate(BaseModel):
    wa_id: str
    name: Optional[str] = None
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    address: Optional[str] = None
    email: Optional[EmailStr] = None

# Schema for outputting a customer
class CustomerOut(BaseModel):
    id: UUID
    wa_id: str
    name: Optional[str] = None
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    user_id: Optional[UUID] = None
    customer_status: Optional[CustomerStatusEnum] = None

    class Config:
        from_attributes = True

# Schema for updating name/address (but NOT email)
class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    address: Optional[str] = None

# ✅ Separate schema for updating ONLY email
class CustomerEmailUpdate(BaseModel):
    email: EmailStr

# Assign user to customer
class AssignUserRequest(BaseModel):
    user_id: Optional[UUID] = None
class CustomerStatusEnum(str, Enum):
    pending = "pending"
    open = "open"
    resolved = "resolved"

class CustomerStatusUpdate(BaseModel):
    status: CustomerStatusEnum