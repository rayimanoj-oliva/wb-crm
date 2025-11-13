from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta

from models.models import Message, Customer, ReferrerTracking
from clients.schema import AppointmentQuery
import clients.service as client_service
from models.models import Template, JobStatus


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


def get_appointments_booked_today(center_id: Optional[str] = None, db: Session = None):
    """
    Count appointments booked today from treatment flow.
    An appointment is considered booked when user reaches the "Thank you" message step.
    """
    if db is None:
        return 0
    
    today = date.today()
    
    # Count appointments from ReferrerTracking where:
    # 1. is_appointment_booked = True (appointment was booked)
    # 2. created_at is today (booked today)
    query = db.query(ReferrerTracking).filter(
        ReferrerTracking.is_appointment_booked == True,
        func.date(ReferrerTracking.created_at) == today
    )
    
    # Optionally filter by center_id if provided
    if center_id:
        # Try to match center_id with center_name or location
        query = query.filter(
            (ReferrerTracking.center_name.ilike(f"%{center_id}%")) |
            (ReferrerTracking.location.ilike(f"%{center_id}%"))
        )
    
    count = query.count()
    return count

def get_agent_avg_response_time(agent_id: str, center_id: Optional[str], db: Session) -> Optional[float]:
    """
    Calculates the average time taken by a specific agent to reply to a customer message.

    The function uses the 'agent_id' and the optional 'center_id' to filter messages.

    :param agent_id: The ID of the agent whose response time is being measured.
    :param center_id: The ID of the center to filter messages by. Optional.
    :param db: The database session.
    :return: The average response time in seconds, or None if no agent replies are found.
    """
    # Start with a base query for all messages related to the agent
    query = db.query(Message).filter(
        Message.agent_id == agent_id
    )

    # If a center_id is provided, add the filter
    if center_id:
        query = query.filter(Message.center_id == center_id)

    # Order the messages by timestamp for accurate calculation
    messages = query.order_by(Message.timestamp).all()

    if not messages:
        return None

    response_times = []
    last_customer_message_time = None

    for message in messages:
        # Check if the current message is from a customer
        if message.sender_type == "customer":
            last_customer_message_time = message.timestamp
        # Check if the current message is from the specified agent and we have a preceding customer message
        elif message.sender_type == "agent" and message.agent_id == agent_id and last_customer_message_time:
            # Calculate the time difference
            time_diff: timedelta = message.timestamp - last_customer_message_time
            response_times.append(time_diff.total_seconds())
            # Reset the last customer message time, as this response concludes the sequence
            last_customer_message_time = None

    if not response_times:
        return None  # No agent replies found

    # Calculate the average response time
    avg_response_time = sum(response_times) / len(response_times)
    return avg_response_time
def get_template_status(db: Session):
    """
    Returns counts of approved, pending, and rejected templates
    """
    # Status stored from Meta is typically uppercase (e.g., "APPROVED", "PENDING", "REJECTED").
    # Normalize to lowercase for robust matching.
    status_expr = func.lower(Template.template_body["status"].astext)

    approved = db.query(Template).filter(status_expr == "approved").count()

    # Treat various review-like states as pending review
    pending_statuses = ["pending", "in_appeal", "in_review", "review"]
    pending = db.query(Template).filter(status_expr.in_(pending_statuses)).count()

    rejected = db.query(Template).filter(status_expr == "rejected").count()

    return {
        "approved": approved,
        "pending": pending,
        "failed": rejected,
    }


def get_recent_failed_messages(db: Session):
    """
    Returns counts of different failure reasons in recent JobStatus / Message failures
    """
    # Example: if you are storing failures in JobStatus with "failure" + reason in body
    unapproved_template = db.query(Message).filter(Message.body.ilike("%Unapproved template%")).count()
    user_opted_out = db.query(Message).filter(Message.body.ilike("%opted out%")).count()
    invalid_phone = db.query(Message).filter(Message.body.ilike("%Invalid phone%")).count()

    return {
        "unapproved_template_used": unapproved_template,
        "user_opted_out": user_opted_out,
        "invalid_phone_number": invalid_phone
    }