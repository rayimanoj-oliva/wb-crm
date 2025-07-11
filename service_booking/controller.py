from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db
from service_booking.schema import BookingRequest, BookingResponse,SlotResponse,SlotReserveRequest, SlotReserveResponse,ConfirmSlotRequest,CancelBookingRequest,RescheduleBookingRequest
from service_booking.service import create_booking,get_available_slots,reserve_slot,confirm_slot_with_zenoti,cancel_booking, reschedule_booking

router = APIRouter()

@router.post("/book_service", response_model=BookingResponse)
def book_service_handler(req: BookingRequest, db: Session = Depends(get_db)):
    return create_booking(req, db)

@router.get("/booking_slots/{booking_id}", response_model=SlotResponse)
def get_slots_handler(booking_id: str, db: Session = Depends(get_db)):
    return get_available_slots(booking_id, db)

@router.post("/reserve_slot", response_model=SlotReserveResponse)
def reserve_slot_handler(req: SlotReserveRequest, db: Session = Depends(get_db)):
    return reserve_slot(req, db)

@router.post("/confirm_slot")
def confirm_slot_handler(req: ConfirmSlotRequest, db: Session = Depends(get_db)):
    return confirm_slot_with_zenoti(req, db)


@router.put("/cancel_booking")
def cancel_booking_handler(
    req: CancelBookingRequest,
    db: Session = Depends(get_db)
):
    return cancel_booking(req, db)

@router.post("/reschedule_booking")
def reschedule_booking_handler(req: RescheduleBookingRequest, db: Session = Depends(get_db)):
    return reschedule_booking(req, db)

