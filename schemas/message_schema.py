from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class MessageCreate(BaseModel):
    message_id: str
    from_wa_id: str
    to_wa_id: str
    type: str
    body: str
    timestamp: datetime
    customer_id: UUID

    # Optional media fields
    media_id: Optional[str] = None
    caption: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None

class MessageOut(BaseModel):
    id: int
    message_id: str
    from_wa_id: str
    to_wa_id: str
    type: str
    body: str
    timestamp: datetime
    customer_id: UUID

    # Optional media fields
    media_id: Optional[str] = None
    caption: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None

    class Config:
        orm_mode = True