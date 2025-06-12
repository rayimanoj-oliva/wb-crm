from sqlalchemy.orm import Session
from models.models import WhatsAppToken
from schemas.WhatsappToken import WhatsAppTokenCreate

def create_whatsapp_token(db: Session, token_data: WhatsAppTokenCreate):
    token_entry = WhatsAppToken(token=token_data.token)
    db.add(token_entry)
    db.commit()
    db.refresh(token_entry)
    return token_entry
