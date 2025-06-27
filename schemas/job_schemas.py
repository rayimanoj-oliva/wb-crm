from pydantic import BaseModel
from typing import List
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
    statuses: List[JobStatusOut]

    class Config:
        orm_mode = True

