# schemas/message_schema.py
from pydantic import BaseModel, Field, RootModel
from typing import List, Dict, Any

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
        from_attributes = True

# ----------- Meta Template Creation Example Values -----------

class TemplateExample(BaseModel):
    header_handle: Optional[List[str]] = None  # For IMAGE headers
    header_text: Optional[List[str]] = None
    body_text: Optional[List[str]] = None



# ----------- Component Definition for Meta Template -----------

class TemplateComponent(BaseModel):
    type: str                      # HEADER, BODY, FOOTER, BUTTONS
    format: Optional[str] = None   # TEXT, IMAGE (only for HEADER)
    text: Optional[str] = None     # Message content with placeholders
    example: Optional[TemplateExample] = None


# ----------- Meta Template Create Schema -----------

class CreateMetaTemplateRequest(BaseModel):
    name: str                      # Unique template name (e.g. "promo_offer")
    language: str                  # ISO language code (e.g. "en_US")
    category: str                  # MARKETING, TRANSACTIONAL, OTP
    components: List[TemplateComponent]


class TemplateStructure(RootModel[Dict[str, Any]]):
    pass