# schemas/message_schema.py
from pydantic import BaseModel
from typing import List,Dict

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
    class Config:
        orm_mode = True