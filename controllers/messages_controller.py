from fastapi import APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database.db import get_db
from models.models import WhatsAppMessage
from schemas.MessageSchema import MessageRead

router = APIRouter()

@router.get("/messages", response_model=list[MessageRead])
def get_messages(db: Session = Depends(get_db)):
    messages = db.query(WhatsAppMessage).order_by(WhatsAppMessage.timestamp.desc()).all()
    return messages
