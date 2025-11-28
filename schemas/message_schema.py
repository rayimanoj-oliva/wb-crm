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

    # Sender metadata
    agent_id: Optional[str] = None
    sender_type: Optional[str] = None

    # Optional location fields
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Optional media fields
    media_id: Optional[str] = None
    caption: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    agent_id: Optional[str] = None
    sender_type: Optional[str] = None
    agent_name: Optional[str] = None

    class Config:
        from_attributes = True
