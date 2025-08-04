from sqlalchemy.orm import Session
from sqlalchemy import or_
from cache.service import increment_unread, reset_unread
from models.models import Message, Customer
from schemas.message_schema import MessageCreate
from datetime import datetime

def create_message(db: Session, message_data: MessageCreate) -> Message:
    new_message = Message(
        message_id=message_data.message_id,
        from_wa_id=message_data.from_wa_id,
        to_wa_id=message_data.to_wa_id,
        type=message_data.type,
        body=message_data.body,
        timestamp=message_data.timestamp or datetime.utcnow(),
        customer_id=message_data.customer_id,
        media_id=message_data.media_id,
        caption=message_data.caption,
        filename=message_data.filename,
        mime_type=message_data.mime_type,
    )
    customer = db.query(Customer).filter(Customer.id == message_data.customer_id).first()
    if customer:
        customer.last_message_at = new_message.timestamp

    increment_unread(message_data.from_wa_id)
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    return new_message


def get_messages_by_customer_uuid(db: Session, customer_uuid: str):
    # Validate UUID here if needed (outside this function)
    return db.query(Message).filter(Message.customer_id == customer_uuid).order_by(Message.timestamp.asc()).all()


def get_messages_by_wa_id(db: Session, wa_id: str):
    reset_unread(wa_id)
    return db.query(Message).filter(
        or_(
            Message.from_wa_id == wa_id,
            Message.to_wa_id == wa_id
        )
    ).order_by(Message.timestamp.asc()).all()
