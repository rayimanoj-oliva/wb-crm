from datetime import datetime

from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

class CustomerCreate(BaseModel):
    wa_id: str
    name: Optional[str] = None

class CustomerOut(BaseModel):
    id: UUID
    wa_id: str
    name: Optional[str] = None
    unread_count: int = 0
    last_message_at: Optional[datetime] = None  # ✅ added this line

    class Config:
        orm_mode = True

class CustomerUpdate(BaseModel):
    name: str
