from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

class CustomerCreate(BaseModel):
    wa_id: str
    name: Optional[str] = None

class CustomerOut(BaseModel):
    id: int
    wa_id: str
    name: Optional[str] = None

    class Config:
        orm_mode = True
