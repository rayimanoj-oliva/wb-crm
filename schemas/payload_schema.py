from fastapi import Body
from pydantic import BaseModel, Field
from typing import Optional, Literal, Union
from datetime import datetime
import requests

# ---- Define request schema ----

class TextPayload(BaseModel):
    type: Literal["text"]
    wa_id: str
    body: str

class ImagePayload(BaseModel):
    type: Literal["image"]
    wa_id: str
    image: dict = Field()
    """example={
        "id": "MEDIA_ID",
         "caption": "some caption"
     }"""

class DocumentPayload(BaseModel):
    type: Literal["document"]
    wa_id: str
    document: dict = Field()
    """example={
        "id": "MEDIA_ID",
        "caption": "some caption",
        "filename": "resume.pdf"
    }"""

MessagePayload = Union[TextPayload, ImagePayload, DocumentPayload]
