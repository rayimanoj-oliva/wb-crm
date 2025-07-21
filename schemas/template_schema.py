# schemas/message_schema.py
from pydantic import BaseModel
from typing import List,Dict

from typing_extensions import Optional

class TemplateComponent(BaseModel):
    type: str
    format: Optional[str] = None
    text: Optional[str] = None
    example: Optional[Dict] = None


# ----------- Single Meta Template -----------

class TemplateMetaItem(BaseModel):
    name: str
    language: str
    status: str
    category: Optional[str]
    components: Optional[List[TemplateComponent]]


# ----------- Meta Template API Response -----------

class TemplatesResponse(BaseModel):
    data: List[TemplateMetaItem]

class TemplateParameter(BaseModel):
    type: str = "text"
    text: str

class SendTemplateRequest(BaseModel):
    to: str
    template_name: str
    parameters: List[TemplateParameter]

class TemplateBase(BaseModel):
    template_body: Dict
    template_vars: Dict



class TemplateCreate(TemplateBase):
    template_name: str

class TemplateUpdate(TemplateBase):
    pass

class TemplateOut(TemplateCreate):
    id: Optional[int]  # Add ID if using in response
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    class Config:
        orm_mode = True