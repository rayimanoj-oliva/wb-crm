
import requests
from fastapi import HTTPException
from service_booking.schema import BookingRequest, BookingResponse,SlotResponse,SlotReserveRequest, SlotReserveResponse, ConfirmSlotRequest,CancelBookingRequest,RescheduleBookingRequest
from service_booking.zenoti_api import BASE_URL, ZENOTI_API_KEY,ZENOTI_HEADERS
import json
from sqlalchemy.orm import Session
from service_booking.model import Booking, ReservedSlot, ConfirmedBooking, RescheduleLog
from datetime import datetime

def create_booking(req: BookingRequest, db: Session) -> BookingResponse:
    payload = {
        "center_id": req.center_id,
        "date": req.date,
        "is_only_catalog_employees": False,
        "use_online_booking_template": True,
        "is_couple_service": False,
        "guests": [{
            "id": req.guest_id,
            "items": [{
                "item": {"id": req.service_id}
            }]
        }]
    }
    try:
        response = requests.post(
            f"{BASE_URL}/bookings?is_double_booking_enabled=true",
            headers=ZENOTI_HEADERS,
            json=payload
        )
        print("Zenoti response:", response.status_code, response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        print("ERROR during booking:", e)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Zenoti API error: {str(e)}")
    data = response.json()
    booking_id = data.get("id")
    if not booking_id:
        raise HTTPException(status_code=500, detail="Zenoti did not return a booking_id")
    # Store in DB
    db_booking = Booking(
        booking_id=booking_id,
        guest_id=req.guest_id,
        center_id=req.center_id,
        booking_date=req.date,
        date=req.date,
        service_item_id=req.service_id,
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return BookingResponse(
        status="success",
        message="Booking created successfully",
        booking_id=booking_id
    )

def get_available_slots(booking_id: str, db: Session) -> SlotResponse:
    try:
        url = f"{BASE_URL}/bookings/{booking_id}/slots?check_future_day_availability=true"
        response = requests.get(url, headers=ZENOTI_HEADERS)
        response.raise_for_status()
    except requests.RequestException as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch slots: {str(e)}")
    data = response.json()
    slots = data.get("slots", [])
    if not slots:
        raise HTTPException(status_code=404, detail="No slots found for this booking")
    return SlotResponse(
        booking_id=booking_id,
        available_slots=[slot["Time"] for slot in slots if slot.get("Available", False)]
    )

def reserve_slot(req: SlotReserveRequest, db: Session) -> SlotReserveResponse:
    payload = {
        "slot_time": req.slot_time,
        "create_invoice": True
    }
    try:
        response = requests.post(
            f"{BASE_URL}/bookings/{req.booking_id}/slots/reserve",
            headers=ZENOTI_HEADERS,
            json=payload
        )
        print("Reserve slot response:", response.status_code, response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        print("ERROR reserving slot:", e)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Zenoti API error: {str(e)}")

    # ✅ Extract valid UUID from response
    data = response.json()
    zenoti_reservation_id = data.get("reservation_id")

    if not zenoti_reservation_id:
        raise HTTPException(status_code=500, detail="Zenoti response missing reservation_id")

    # Store in DB
    db_slot = ReservedSlot(
        reservation_id=zenoti_reservation_id,  
        booking_id=req.booking_id,
        slot_time=req.slot_time,
        create_invoice=True,
        response_snapshot=response.text
    )
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)

    return SlotReserveResponse(
        status="success",
        message="Slot reserved successfully"
    )


def confirm_slot_with_zenoti(req: ConfirmSlotRequest, db: Session):
    url = f"{BASE_URL}/bookings/{req.booking_id}/slots/confirm"
    try:
        response = requests.post(
            url,
            headers=ZENOTI_HEADERS,
            json={"center_id": req.center_id}
        )
        print("Zenoti confirm response:", response.status_code, response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Zenoti confirm error: {str(e)}")

    data = response.json()
    if not data.get("is_confirmed"):
        raise HTTPException(status_code=400, detail="Booking not confirmed")

    invoice = data.get("invoice", {})
    guest = invoice.get("guest", {})
    items = invoice.get("items", [])
    item = items[0] if items else {}
    therapist = item.get("therapist", {})
    room = item.get("room", {})

    db_confirm = ConfirmedBooking(
        appointment_id=item.get("appointment_id", req.booking_id),
        booking_id=req.booking_id,
        guest_id=guest.get("Id"),
        guest_first_name=guest.get("FirstName"),
        guest_last_name=guest.get("LastName"),
        invoice_id=invoice.get("invoice_id"),
        item_id=item.get("item", {}).get("id"),
        item_name=item.get("item", {}).get("name"),
        item_type=item.get("item", {}).get("item_type"),
        item_display_name=item.get("item", {}).get("item_display_name"),
        therapist_id=therapist.get("id"),
        therapist_full_name=therapist.get("full_name"),
        therapist_first_name=therapist.get("first_name"),
        therapist_last_name=therapist.get("last_name"),
        therapist_request_type=therapist.get("therapist_request_type"),
        room_id=room.get("id"),
        room_name=room.get("name"),
        start_time=item.get("start_time"),
        end_time=item.get("end_time"),
        invoice_item_id=item.get("invoice_item_id"),
        join_link=item.get("join_link"),
        created_at=datetime.utcnow()
    )

    db.add(db_confirm)
    db.commit()
    db.refresh(db_confirm)

    return {
        "status": "success",
        "message": "Booking confirmed",
        "appointment_id": item.get("appointment_id", req.booking_id),
        "invoice_id": invoice.get("invoice_id")
    }

def cancel_booking(req: CancelBookingRequest, db: Session):
    url = f"{BASE_URL}/invoices/{req.invoice_id}/cancel?comments={req.comments}"

    try:
        response = requests.put(
            url,
            headers=ZENOTI_HEADERS,
            json={"comments": req.comments}
        )
        print("Zenoti cancel response:", response.status_code, response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Zenoti cancel error: {str(e)}")

    # Update status locally
    booking = db.query(ConfirmedBooking).filter_by(invoice_id=req.invoice_id).first()
    if booking:
        booking.status = "cancelled"
        booking.cancelled_at = datetime.utcnow()  
        db.commit()

    return {
        "status": "success",
        "message": "Booking cancelled successfully"
    }

def reschedule_booking(req: RescheduleBookingRequest, db: Session):
    url = f"{BASE_URL}/bookings"
    payload = {
        "center_id": req.center_id,
        "date": req.date,
        "is_only_catalog_employees": False,
        "guests": [
            {
                "id": req.guest_id,
                "invoice_id": req.invoice_id,
                "items": [
                    {
                        "item": {
                            "id": req.item_id
                        },
                        "therapist": {
                            "id": req.therapist_id
                        },
                        "invoice_item_id": req.invoice_item_id
                    }
                ]
            }
        ]
    }
    try:
        response = requests.post(
            url,
            headers=ZENOTI_HEADERS,
            json=payload
        )
        print("Zenoti reschedule response:", response.status_code, response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Zenoti reschedule error: {str(e)}")
    data = response.json()
    booking_id = data.get("id")
    if not booking_id:
        raise HTTPException(status_code=500, detail="Zenoti did not return a new booking ID")
    # Store reschedule log in DB
    db_log = RescheduleLog(
    old_booking_id=req.old_booking_id,   
    new_booking_id=booking_id,
    invoice_id=req.invoice_id,
    invoice_item_id=req.invoice_item_id
)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return {
        "status": "success",
        "message": "Booking rescheduled successfully",
        "booking_id": booking_id
    }
