from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QuickReplyBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=2000, description="The message body to insert")
    category: Optional[str] = Field(default=None, max_length=120)


class QuickReplyCreate(QuickReplyBase):
    pass


class QuickReplyUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=120)


class QuickReplyOut(QuickReplyBase):
    id: UUID
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class QuickReplyListResponse(BaseModel):
    items: list[QuickReplyOut]
    total: int


