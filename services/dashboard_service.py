from sqlalchemy.orm import Session
from datetime import datetime, date

from models.models import Message, Customer


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