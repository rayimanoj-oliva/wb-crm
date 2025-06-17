from uuid import UUID

from pydantic import BaseModel
from typing import List
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

class OrderItemOut(OrderItemCreate):
    id: int

    class Config:
        orm_mode = True

class OrderOut(BaseModel):
    id: int
    customer_id: UUID
    catalog_id: str
    timestamp: datetime
    items: List[OrderItemOut]

    class Config:
        orm_mode = True