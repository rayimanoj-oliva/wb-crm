from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime

class JobStatusOut(BaseModel):
    customer_id: UUID
    status: str

    class Config:
        orm_mode = True

class JobOut(BaseModel):
    id: UUID
    campaign_id: UUID
    created_at: datetime
    last_attempted_by: Optional[UUID] = None
    last_triggered_time: Optional[datetime] = None
    statuses: List[JobStatusOut]

    class Config:
        orm_mode = True
