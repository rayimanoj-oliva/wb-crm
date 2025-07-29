from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, date

from models.models import Message, Customer
from clients.schema import AppointmentQuery
import clients.service as client_service

def get_today_metrics(db: Session):
    today = date.today()

    # Get new conversations (messages created today)
    new_conversations = db.query(Message).filter(
        Message.timestamp >= datetime.combine(today, datetime.min.time()),
        Message.timestamp <= datetime.combine(today, datetime.max.time())
    ).count()

    # Get new customers created today
    new_customers = db.query(Customer).filter(
        Customer.created_at >= datetime.combine(today, datetime.min.time()),
        Customer.created_at <= datetime.combine(today, datetime.max.time())
    ).count()

    return {
        "new_conversations": new_conversations,
        "new_customers": new_customers
    }



def get_total_customers(db: Session):
    return db.query(Customer).count()


def get_appointments_booked_today(center_id: str, db: Session):
    today = date.today()

    # Build the query object for today's date
    query = AppointmentQuery(
        center_id=center_id,
        start_date=today,
        end_date=today
    )

    # Fetch appointments using existing logic
    appointments = client_service.fetch_appointments(query)

    return len(appointments)