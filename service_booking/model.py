from sqlalchemy import Column, String, Date, Boolean, DateTime, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Booking(Base):
    __tablename__ = "service_bookings"

    booking_id = Column(String, primary_key=True, index=True)
    guest_id = Column(String, nullable=False)
    center_id = Column(String, nullable=False)
    booking_date = Column(Date, nullable=False)
    date = Column(Date, nullable=True)
    service_item_id = Column(String, nullable=True)
    is_couple_service = Column(Boolean, default=False)
    is_only_catalog_employees = Column(Boolean, default=False)
    use_online_booking_template = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_cancelled = Column(Boolean, default=False)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_comments = Column(Text, nullable=True)


class ReservedSlot(Base):
    __tablename__ = "reserved_slots"

    reservation_id = Column(String, primary_key=True, index=True)
    booking_id = Column(String, nullable=False)
    slot_time = Column(DateTime, nullable=False)
    create_invoice = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    response_snapshot = Column(Text, nullable=True)


class ConfirmedBooking(Base):
    __tablename__ = "confirmed_bookings"

    appointment_id = Column(String, primary_key=True, index=True)
    booking_id = Column(String, index=True)
    guest_id = Column(String)
    guest_first_name = Column(String)
    guest_last_name = Column(String)
    invoice_id = Column(String)
    item_id = Column(String)
    item_name = Column(String)
    item_type = Column(String)
    item_display_name = Column(String)
    therapist_id = Column(String)
    therapist_full_name = Column(String)
    therapist_first_name = Column(String)
    therapist_last_name = Column(String)
    therapist_request_type = Column(String)
    room_id = Column(String)
    room_name = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    invoice_item_id = Column(String)
    join_link = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="confirmed")
    
    cancelled_at = Column(DateTime, nullable=True)

class RescheduleLog(Base):
    __tablename__ = "reschedule_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    old_booking_id = Column(String, nullable=False)
    new_booking_id = Column(String, nullable=False)
    invoice_id = Column(String, nullable=False)
    invoice_item_id = Column(String, nullable=False)
    rescheduled_at = Column(DateTime, default=datetime.utcnow)
