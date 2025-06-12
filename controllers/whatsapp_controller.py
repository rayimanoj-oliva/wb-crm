from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from schemas.WhatsappToken import WhatsAppTokenCreate
from database.db import get_db
from services.whatsapp_service import create_whatsapp_token

router = APIRouter(tags=["WhatsApp Token"])

@router.post("/token", status_code=201)
def add_token(token_data: WhatsAppTokenCreate, db: Session = Depends(get_db)):
    try:
        create_whatsapp_token(db, token_data)
        return {"status": "success", "message": "Token saved securely"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
