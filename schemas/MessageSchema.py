from datetime import datetime

from pydantic import BaseModel


class MessageCreate(BaseModel):
    message_id: str
    from_wa_id: str
    to_wa_id: str
    type: str
    body: str
    timestamp: datetime
    customer_id: int

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
