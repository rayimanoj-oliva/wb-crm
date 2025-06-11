from datetime import datetime

from pydantic import BaseModel
from uuid import UUID

class MessageCreate(BaseModel):
    message_id: str
    from_wa_id: str
    to_wa_id: str
    type: str
    body: str
    timestamp: datetime
    customer_id: UUID

class MessageOut(BaseModel):
    id: int
    message_id: str
    from_wa_id: str
    to_wa_id: str
    type: str
    body: str
    timestamp: datetime
    customer_id: int

    class Config:
        orm_mode = True
