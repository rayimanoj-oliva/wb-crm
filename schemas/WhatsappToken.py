from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class WhatsAppTokenCreate(BaseModel):
    token: str

class WhatsAppTokenResponse(BaseModel):
    id: UUID
    token: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
