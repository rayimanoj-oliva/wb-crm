"""
Referrer tracking schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ReferrerTrackingBase(BaseModel):
    wa_id: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    referrer_url: Optional[str] = None
    center_name: Optional[str] = None
    location: Optional[str] = None
    customer_id: Optional[UUID] = None


class ReferrerTrackingCreate(ReferrerTrackingBase):
    pass


class ReferrerTrackingResponse(ReferrerTrackingBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class ReferrerTrackingUpdate(BaseModel):
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    referrer_url: Optional[str] = None
    center_name: Optional[str] = None
    location: Optional[str] = None
