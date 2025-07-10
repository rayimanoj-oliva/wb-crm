from pydantic import BaseModel
from typing import List

class CenterInfo(BaseModel):
    center_id: str
    center_name: str

class CenterNamesResponse(BaseModel):
    centers: List[CenterInfo]
