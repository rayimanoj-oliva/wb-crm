from datetime import datetime , date
from pydantic import BaseModel
from typing import Optional


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
    Phone: Optional[str]
class LeadQuery(BaseModel):
    from_datetime: datetime
    to_datetime: datetime