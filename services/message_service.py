from sqlalchemy.orm import Session

from cache.service import increment_unread, reset_unread
from models.models import Message, Customer
from schemas.message_schema import MessageCreate
from datetime import datetime

# Create a new message
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



# Get a message by its ID
def get_message_by_id(db: Session, message_id: int) -> Message:
    return db.query(Message).filter(Message.id == message_id).first()


# List all messages (with optional pagination)
def get_all_messages(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Message).offset(skip).limit(limit).all()


# Get all messages for a specific customer
def get_messages_by_customer_id(db: Session, customer_id: int):
    return db.query(Message).filter(Message.customer_id == customer_id).all()


# Update a message (by database ID)
def update_message(db: Session, message_id: int, updated_data: MessageCreate) -> Message:
    message = get_message_by_id(db, message_id)
    if message:
        message.message_id = updated_data.message_id
        message.from_wa_id = updated_data.from_wa_id
        message.to_wa_id = updated_data.to_wa_id
        message.type = updated_data.type
        message.body = updated_data.body
        message.timestamp = updated_data.timestamp
        message.customer_id = updated_data.customer_id
        db.commit()
        db.refresh(message)
    return message


# Delete a message
def delete_message(db: Session, message_id: int):
    message = get_message_by_id(db, message_id)
    if message:
        db.delete(message)
        db.commit()
    return message

def get_messages_by_wa_id(db: Session, wa_id: str):

    return db.query(Message).filter(
        (Message.from_wa_id == wa_id) | (Message.to_wa_id == wa_id)
    ).order_by(Message.timestamp.asc()).all()