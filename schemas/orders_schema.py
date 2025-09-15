from uuid import UUID

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class OrderItemCreate(BaseModel):
    product_retailer_id: str
    quantity: int
    item_price: float
    currency: str

class OrderCreate(BaseModel):
    customer_id: UUID
    catalog_id: str
    timestamp: datetime
    items: List[OrderItemCreate]

class OrderItemOut(BaseModel):
    product_retailer_id: str
    quantity: int
    item_price: float
    currency: str

    class Config:
        orm_mode = True

class OrderOut(BaseModel):
    id: UUID
    catalog_id: Optional[str]
    timestamp: datetime
    items: List[OrderItemOut]

    class Config:
        orm_mode = True

class PaymentCreate(BaseModel):
    order_id: UUID
    amount: float
    currency: str = "INR"

class PaymentOut(BaseModel):
    id: UUID
    order_id: UUID
    amount: float
    currency: str
    razorpay_id: Optional[str]
    razorpay_short_url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True