"""
Organization schemas for API requests and responses
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Organization name")
    slug: Optional[str] = Field(None, max_length=255, description="URL-friendly slug")
    description: Optional[str] = Field(None, description="Organization description")
    is_active: bool = Field(True, description="Whether the organization is active")


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrganizationResponse(OrganizationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    total: int

