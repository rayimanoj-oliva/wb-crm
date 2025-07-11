from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from schemas.message_schema import MessageCreate, MessageOut
from services import message_service
from database.db import get_db
from services.message_service import get_messages_by_wa_id

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
def list_messages_by_customer(customer_id: int, db: Session = Depends(get_db)):
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
def get_user_messages(wa_id: str, db: Session = Depends(get_db)):
    messages = get_messages_by_wa_id(db, wa_id)
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this wa_id")
    return messages