# schemas/message_schema.py
from pydantic import BaseModel
from typing import List

class TemplateParameter(BaseModel):
    type: str = "text"
    text: str

class SendTemplateRequest(BaseModel):
    to: str
    template_name: str
    parameters: List[TemplateParameter]
