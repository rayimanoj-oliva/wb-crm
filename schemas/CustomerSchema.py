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

    class Config:
        orm_mode = True

class CustomerUpdate(BaseModel):
    name: str
