from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import uuid
from schemas.message_schema import MessageCreate, MessageOut
from services import message_service
from database.db import get_db
from services.message_service import get_messages, get_customer_wa_ids_by_business_number, get_customer_wa_ids_by_date, get_customer_wa_ids_pending_agent_reply
from models.models import User

router = APIRouter(
    tags=["Messages"]
)

# Create a message
@router.post("/", response_model=MessageOut)
def create_message(data: MessageCreate, db: Session = Depends(get_db)):
    return message_service.create_message(db, data)


# Get a message by DB ID
@router.get("/{message_id}", response_model=MessageOut)
def read_message(message_id: int, db: Session = Depends(get_db)):
    message = message_service.get_message_by_id(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


# List all messages
@router.get("/", response_model=List[MessageOut])
def list_messages(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return message_service.get_all_messages(db, skip, limit)


# Get messages for a specific customer
@router.get("/customer/{customer_id}", response_model=List[MessageOut])
def list_messages_by_customer(customer_id: UUID, db: Session = Depends(get_db)):
    return message_service.get_messages_by_customer_id(db, customer_id)


# Update a message by DB ID
@router.put("/{message_id}", response_model=MessageOut)
def update_message(message_id: int, data: MessageCreate, db: Session = Depends(get_db)):
    message = message_service.update_message(db, message_id, data)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


# Delete a message by DB ID
@router.delete("/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db)):
    message = message_service.delete_message(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "deleted", "message_id": message_id}


@router.get("/chat/{wa_id}", response_model=List[MessageOut])
def get_chat(
    wa_id: str,
    peer: str | None = Query(None, description="Optional other wa_id to filter chat with"),
    db: Session = Depends(get_db),
):
    messages = get_messages(db, wa_id, peer)

    if not messages:
        raise HTTPException(
            status_code=404,
            detail="No messages found"
        )

    agent_ids = {msg.agent_id for msg in messages if getattr(msg, "agent_id", None)}
    if agent_ids:
        parsed_ids = []
        for agent_id in agent_ids:
            try:
                parsed_ids.append(uuid.UUID(str(agent_id)))
            except (ValueError, TypeError):
                continue
        if parsed_ids:
            users = db.query(User).filter(User.id.in_(parsed_ids)).all()
            agent_map = {
                str(user.id): (f"{user.first_name} {user.last_name}".strip() or user.username or user.email)
                for user in users
            }
            for message in messages:
                agent_name = agent_map.get(getattr(message, "agent_id", None))
                if agent_name:
                    setattr(message, "agent_name", agent_name)

    return messages


@router.get("/customers/by-business-number/{business_number}")
def get_customers_by_business_number(
    business_number: str,
    db: Session = Depends(get_db),
):
    """
    Get all customer wa_ids that have messages with a specific business number.
    
    This endpoint is useful for filtering conversations by business number on the frontend.
    """
    customer_wa_ids = get_customer_wa_ids_by_business_number(db, business_number)
    return {"customer_wa_ids": customer_wa_ids}


@router.get("/customers/by-date/{date}")
def get_customers_by_date(
    date: str,
    db: Session = Depends(get_db),
):
    """
    Get all customer wa_ids that have messages on a specific date.
    
    Args:
        date: Date string in format 'YYYY-MM-DD' (e.g., "2025-11-14")
    
    This endpoint is useful for filtering conversations by date on the frontend.
    """
    customer_wa_ids = get_customer_wa_ids_by_date(db, date)
    return {"customer_wa_ids": customer_wa_ids}


@router.get("/customers/pending-agent-reply")
def get_customers_pending_agent_reply(
    db: Session = Depends(get_db),
):
    """
    Get all customer wa_ids where the latest message was sent by the customer,
    indicating the conversation is awaiting an agent reply.
    """
    customer_wa_ids = get_customer_wa_ids_pending_agent_reply(db)
    return {"customer_wa_ids": customer_wa_ids}

