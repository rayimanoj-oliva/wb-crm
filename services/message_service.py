from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

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


# Get all messages involving a specific wa_id (either as sender or receiver)
def get_messages_by_wa_id(db: Session, wa_id: str):
    """Get all messages where the given wa_id is either the sender or receiver.
    
    Args:
        db: Database session
        wa_id: WhatsApp ID to search for
        
    Returns:
        List of all messages involving this wa_id
    """
    return db.query(Message).filter(
        (Message.from_wa_id == wa_id) | (Message.to_wa_id == wa_id)
    ).order_by(Message.timestamp.asc()).all()


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

def get_messages(db: Session, wa_id: str, peer: str | None):
    
    base_query = db.query(Message).filter(
        (Message.from_wa_id == wa_id) | (Message.to_wa_id == wa_id)
    )

    # If peer is NOT provided → return all messages involving wa_id
    if not peer:
        reset_unread(wa_id)  # optional
        return base_query.order_by(Message.timestamp.asc()).all()

    # If peer IS provided → return only messages between wa_id and peer
    reset_unread(wa_id)  # optional
    return (
        base_query.filter(
            or_(
                and_(Message.from_wa_id == wa_id, Message.to_wa_id == peer),
                and_(Message.from_wa_id == peer, Message.to_wa_id == wa_id),
            )
        )
        .order_by(Message.timestamp.asc())
        .all()
    )


def get_customer_wa_ids_by_date(db: Session, target_date: str) -> list[str]:
    """
    Get all customer wa_ids that have messages on a specific date.
    
    Args:
        db: Database session
        target_date: Date string in format 'YYYY-MM-DD' (e.g., "2025-11-14")
    
    Returns:
        List of unique customer wa_ids that have messages on the target date
    """
    from sqlalchemy import distinct, func, cast, Date
    from datetime import datetime
    
    try:
        # Parse the target date
        target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
        start_datetime = datetime.combine(target_dt, datetime.min.time())
        end_datetime = datetime.combine(target_dt, datetime.max.time())
        
        # Find all unique customer wa_ids that have messages on this date
        # Messages can be either from customer (from_wa_id) or to customer (to_wa_id)
        # We need to get the customer's wa_id, not the business number
        
        # Get wa_ids from messages where customer sent a message (from_wa_id is customer)
        from_customer = (
            db.query(distinct(Message.from_wa_id))
            .filter(
                Message.timestamp >= start_datetime,
                Message.timestamp <= end_datetime
            )
            .all()
        )
        
        # Get wa_ids from messages where customer received a message (to_wa_id is customer)
        to_customer = (
            db.query(distinct(Message.to_wa_id))
            .filter(
                Message.timestamp >= start_datetime,
                Message.timestamp <= end_datetime
            )
            .all()
        )
        
        # Combine and extract wa_ids, excluding business numbers
        customer_wa_ids_set = set()
        business_numbers = {'917729992376', '917617613030', '918297882978', '7729992376', '7617613030', '8297882978'}
        
        for wa_id_tuple in from_customer:
            if wa_id_tuple[0]:
                wa_id = wa_id_tuple[0]
                # Extract last 10 digits to check if it's a business number
                digits = ''.join(filter(str.isdigit, wa_id))
                last10 = digits[-10:] if len(digits) >= 10 else digits
                if last10 not in business_numbers and wa_id not in business_numbers:
                    customer_wa_ids_set.add(wa_id)
        
        for wa_id_tuple in to_customer:
            if wa_id_tuple[0]:
                wa_id = wa_id_tuple[0]
                digits = ''.join(filter(str.isdigit, wa_id))
                last10 = digits[-10:] if len(digits) >= 10 else digits
                if last10 not in business_numbers and wa_id not in business_numbers:
                    customer_wa_ids_set.add(wa_id)
        
        return list(customer_wa_ids_set)
    except Exception as e:
        print(f"Error in get_customer_wa_ids_by_date: {e}")
        return []


def get_customer_wa_ids_by_business_number(db: Session, business_number: str) -> list[str]:
    """
    Get all customer wa_ids that have messages with a specific business number.
    
    Args:
        db: Database session
        business_number: The business WhatsApp number (e.g., "917729992376" or "7729992376")
    
    Returns:
        List of unique customer wa_ids that have exchanged messages with the business number
    """
    from sqlalchemy import distinct
    import re
    
    # Normalize the business number to handle different formats
    # Extract digits only and try different formats
    digits = re.sub(r'\D', '', business_number)
    if len(digits) >= 10:
        last10 = digits[-10:]
        # Try different formats: full with 91, with +91, and just last 10 digits
        business_number_variants = [
            business_number,  # Original format
            digits,  # Digits only
            last10,  # Last 10 digits
            f"91{last10}",  # With 91 prefix
            f"+91{last10}",  # With +91 prefix
        ]
        # Remove duplicates while preserving order
        business_number_variants = list(dict.fromkeys(business_number_variants))
    else:
        business_number_variants = [business_number]
    
    # Find all messages where the business number is involved (checking all variants)
    # Business number can be either from_wa_id (business sent to customer) or to_wa_id (customer sent to business)
    customer_wa_ids_set = set()
    
    for variant in business_number_variants:
        # Messages where business sent to customer (from_wa_id = business, to_wa_id = customer)
        from_business = (
            db.query(distinct(Message.to_wa_id))
            .filter(Message.from_wa_id == variant)
            .all()
        )
        for wa_id_tuple in from_business:
            if wa_id_tuple[0] and wa_id_tuple[0] not in business_number_variants:
                customer_wa_ids_set.add(wa_id_tuple[0])
        
        # Messages where customer sent to business (from_wa_id = customer, to_wa_id = business)
        to_business = (
            db.query(distinct(Message.from_wa_id))
            .filter(Message.to_wa_id == variant)
            .all()
        )
        for wa_id_tuple in to_business:
            if wa_id_tuple[0] and wa_id_tuple[0] not in business_number_variants:
                customer_wa_ids_set.add(wa_id_tuple[0])
    
    return list(customer_wa_ids_set)
