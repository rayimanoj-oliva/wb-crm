from pydantic import BaseModel
from datetime import datetime

class MessageCreate(BaseModel):
    wa_id: str
    sender_name: str
    message_id: str
    message_text: str
    timestamp: datetime

class MessageRead(MessageCreate):
    id: int

    class Config:
        orm_mode = True

