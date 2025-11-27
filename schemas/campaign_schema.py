from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional, Literal
from schemas.template_schema import TemplateParameter
from uuid import UUID

# ---- Bulk template sending (direct to wa_ids) ----
class BulkTemplateRecipient(BaseModel):
    """Recipient for bulk template sending - renamed to avoid conflict with SQLAlchemy model"""
    wa_id: str
    parameters: List[TemplateParameter]

class BulkTemplateRequest(BaseModel):
    template_name: str
    clients: List[BulkTemplateRecipient]

# ---- Customer output ----
class CustomerOut(BaseModel):
    id: UUID
    wa_id: str
    name: Optional[str]

    class Config:
        from_attributes = True

# ---- Campaign recipient (Excel uploads) ----
class CampaignRecipientOut(BaseModel):
    id: UUID
    phone_number: str
    name: Optional[str]
    params: Optional[dict]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# ---- Campaign base/create/update ----
AllowedTypes = Literal["text", "image", "document", "template", "interactive"]

class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    customer_ids: Optional[List[UUID]] = []
    content: Optional[dict] = None
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

# ---- Campaign output ----
class CampaignOut(CampaignBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    updated_by: Optional[UUID]
    customers: List[CustomerOut] = []  # CRM linked customers
    recipients: List[CampaignRecipientOut] = []  # Excel-uploaded recipients
    last_job_id: Optional[UUID]

    class Config:
        from_attributes = True


class TemplateCampaignCreateRequest(BaseModel):
    template_name: str
    template_language: str = "en_US"
    campaign_name: str
    description: Optional[str] = None
    image_id: Optional[str] = None
    button_sub_type: Optional[str] = "url"
    button_index: Optional[str] = "1"
    campaign_cost_type: Optional[str] = None


class TemplateExcelColumnsResponse(BaseModel):
    template_name: str
    columns: List[str]
    body_placeholder_count: int
    header_placeholder_count: int
    header_type: Optional[str]
    has_buttons: bool
    button_type: Optional[str]


class TemplateCampaignRunRequest(BaseModel):
    batch_size: int = 100
    batch_delay_seconds: int = 60

