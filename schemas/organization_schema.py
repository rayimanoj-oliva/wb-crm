"""
Organization schemas for API requests and responses
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class WhatsAppNumberBase(BaseModel):
    """Base schema for WhatsApp business numbers linked to an organization."""

    phone_number_id: str = Field(
        ...,
        max_length=100,
        description="WhatsApp Business phone_number_id from Meta",
    )
    display_number: Optional[str] = Field(
        None,
        max_length=50,
        description="Human-readable phone number (e.g., '+91 77299 92376')",
    )
    access_token: Optional[str] = Field(
        None,
        max_length=500,
        description="WhatsApp Business API access token for this number",
    )
    webhook_path: Optional[str] = Field(
        None,
        max_length=255,
        description="Webhook path/endpoint for this number (e.g., '/webhook')",
    )


class WhatsAppNumberCreate(WhatsAppNumberBase):
    """Payload for creating WhatsApp numbers while creating an organization."""

    pass


class WhatsAppNumberResponse(WhatsAppNumberBase):
    """Response schema for WhatsApp numbers associated with an organization."""

    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Organization name")
    code: Optional[str] = Field(None, max_length=50, description="Organization code (e.g., RH0007)")
    slug: Optional[str] = Field(None, max_length=255, description="URL-friendly slug")
    description: Optional[str] = Field(None, description="Organization description")
    is_active: bool = Field(True, description="Whether the organization is active")


class OrganizationCreate(OrganizationBase):
    whatsapp_numbers: List[WhatsAppNumberCreate] = Field(
        default_factory=list,
        description=(
            "List of WhatsApp Business numbers to link with this organization. "
            "Each number will be stored in the whatsapp_numbers table."
        ),
    )


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    slug: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrganizationResponse(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    whatsapp_numbers: List[WhatsAppNumberResponse] = []

    class Config:
        from_attributes = True


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    total: int

