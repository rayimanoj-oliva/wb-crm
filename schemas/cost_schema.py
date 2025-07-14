from pydantic import BaseModel
from typing import List

class CostBase(BaseModel):
    price: float

class CostCreate(CostBase):
    type: str

class CostUpdate(CostBase):
    pass

class CostOut(CostCreate):
    pass
