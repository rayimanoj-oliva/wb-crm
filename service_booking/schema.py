from pydantic import BaseModel, Field
from typing import Optional, List


class BookingRequest(BaseModel):
    guest_id: str = Field(..., example="093ff062-f216-40ca-a10c-86ad4364015b")
    service_id: str = Field(..., example="0ca38d04-cb64-4975-8546-77334a20fb01")
    center_id: str = Field(..., example="90e79e59-6202-4feb-a64f-b647801469e4")
    date: str = Field(..., example="2025-06-17")  


class BookingResponse(BaseModel):
    status: str
    message: str
    booking_id: Optional[str] = None

class SlotResponse(BaseModel):
    booking_id: str
    available_slots: List[str]

class SlotReserveRequest(BaseModel):
    booking_id: str
    slot_time: str  # ISO datetime string like "2025-06-04T16:30:00"

class SlotReserveResponse(BaseModel):
    status: str
    message: str

class ConfirmSlotRequest(BaseModel):
    booking_id: str
    center_id: str
  
class CancelBookingRequest(BaseModel):
    invoice_id: str
    comments: str

class RescheduleBookingRequest(BaseModel):
    old_booking_id: str   
    center_id: str
    date: str
    guest_id: str
    invoice_id: str
    item_id: str
    therapist_id: str
    invoice_item_id: str
