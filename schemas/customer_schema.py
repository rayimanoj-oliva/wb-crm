from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class CustomerCreate(BaseModel):
    wa_id: str
    name: Optional[str] = None
    address: Optional[str] = None   # Add address here

class CustomerOut(BaseModel):
    id: UUID
    wa_id: str
    name: Optional[str] = None
    address: Optional[str] = None   # Add address here
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    user_id: Optional[UUID] = None

    class Config:
        orm_mode = True

class CustomerUpdate(BaseModel):
    name: Optional[str] = None       # Make name optional
    address: Optional[str] = None    # dd address here

class AssignUserRequest(BaseModel):
    user_id: Optional[UUID] = None
