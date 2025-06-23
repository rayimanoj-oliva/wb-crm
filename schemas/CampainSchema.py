from pydantic import BaseModel
from typing import List
from schemas.TemplateSchema import TemplateParameter


class CampaignRecipient(BaseModel):
    wa_id: str
    parameters: List[TemplateParameter]

class BulkTemplateRequest(BaseModel):
    template_name: str
    clients: List[CampaignRecipient]