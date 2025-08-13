from datetime import datetime
from typing import List, Optional, Literal
from uuid import UUID
from pydantic import BaseModel
from schemas.template_schema import TemplateParameter


class CampaignRecipient(BaseModel):
    wa_id: str
    parameters: List[TemplateParameter]  # parameters for template messages


class BulkTemplateRequest(BaseModel):
    template_name: str
    clients: List[CampaignRecipient]


class CustomerOut(BaseModel):
    id: UUID
    wa_id: str
    name: Optional[str]

    class Config:
        orm_mode = True


# Allowed WhatsApp message types for campaigns
AllowedTypes = Literal["text", "image", "document", "template", "interactive"]


class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    customer_ids: Optional[List[UUID]] = []  # linked customer IDs
    content: Optional[dict] = None  # message content or template details
    type: AllowedTypes
    campaign_cost_type: Optional[str] = None


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    customer_ids: Optional[List[UUID]]
    content: Optional[dict]
    type: Optional[AllowedTypes]
    campaign_cost_type: Optional[str] = None


class CampaignOut(CampaignBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    updated_by: Optional[UUID]
    customers: List[CustomerOut]  # include customer details
    last_job_id: Optional[UUID]

    class Config:
        orm_mode = True
