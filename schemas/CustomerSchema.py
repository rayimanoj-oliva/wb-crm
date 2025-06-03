from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

class CustomerBase(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerRead(CustomerBase):
    id: UUID

    class Config:
        orm_mode = True
