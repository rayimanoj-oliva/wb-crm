"""
WhatsApp Number schemas for API requests and responses
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class WhatsAppNumberBase(BaseModel):
    phone_number_id: str = Field(..., min_length=1, max_length=100, description="WhatsApp Business phone_number_id from Meta")
    display_number: Optional[str] = Field(None, max_length=50, description="Human-readable phone number (e.g., +91 77299 92376)")
    access_token: Optional[str] = Field(None, max_length=500, description="WhatsApp Business API access token")
    webhook_path: Optional[str] = Field(None, max_length=255, description="Webhook path/endpoint (e.g., /webhook, /webhook2)")
    organization_id: UUID = Field(..., description="Organization this phone number belongs to")
    is_active: bool = Field(True, description="Whether this phone number is active")


class WhatsAppNumberCreate(WhatsAppNumberBase):
    pass


class WhatsAppNumberUpdate(BaseModel):
    display_number: Optional[str] = Field(None, max_length=50)
    access_token: Optional[str] = Field(None, max_length=500)
    webhook_path: Optional[str] = Field(None, max_length=255)
    organization_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class WhatsAppNumberResponse(WhatsAppNumberBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WhatsAppNumberListResponse(BaseModel):
    items: list[WhatsAppNumberResponse]
    total: int

