from datetime import datetime

from pydantic import BaseModel
from typing import List, Optional, Literal
from schemas.template_schema import TemplateParameter
from uuid import UUID

class CampaignRecipient(BaseModel):
    wa_id: str
    parameters: List[TemplateParameter]

class BulkTemplateRequest(BaseModel):
    template_name: str
    clients: List[CampaignRecipient]

class CustomerOut(BaseModel):
    id: UUID
    wa_id: str
    name: Optional[str]

    class Config:
        orm_mode = True


AllowedTypes = Literal["text", "image", "document", "template", "interactive"]

class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    customer_ids: Optional[List[UUID]] = []
    content: Optional[dict] = None
    type: AllowedTypes

class CampaignCreate(CampaignBase):
    pass

class CampaignUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    customer_ids: Optional[List[UUID]]
    content: Optional[dict]
    type: Optional[AllowedTypes]

class CampaignOut(CampaignBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    updated_by: Optional[UUID]
    customers: List[CustomerOut]  # ✅ include this

    class Config:
        orm_mode = True
