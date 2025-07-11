from pydantic import BaseModel
from typing import Optional
from datetime import date

class AppointmentQuery(BaseModel):
    center_id: str
    start_date: date
    end_date: date

class CollectionQuery(BaseModel):
    centerid: str
    fromdate: date
    todate: date

class SalesQuery(BaseModel):
    center_id: str
    start_date: date
    end_date: date
    item_type: Optional[str] = None
    status: Optional[str] = None

class Lead(BaseModel):
    Last_Name: Optional[str]
    Email: Optional[str]
    Mobile: Optional[str]
    Phone: Optional[str]
