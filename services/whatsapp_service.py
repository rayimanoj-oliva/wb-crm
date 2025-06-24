import json

import pika
from sqlalchemy.orm import Session
from models.models import WhatsAppToken
from schemas.whatsapp_token_schema import WhatsAppTokenCreate

def create_whatsapp_token(db: Session, token_data: WhatsAppTokenCreate):
    token_entry = WhatsAppToken(token=token_data.token)
    db.add(token_entry)
    db.commit()
    db.refresh(token_entry)
    return token_entry

def get_latest_token(db: Session):
    return db.query(WhatsAppToken).order_by(WhatsAppToken.created_at.desc()).first()

def enqueue_template_message(to: str, template_name: str, parameters: list):
    payload = {
        "to": to,
        "template_name": template_name,
        "parameters": [p.model_dump() for p in parameters]
    }
    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    ch = conn.channel()
    ch.queue_declare(queue="whatsapp_campaign", durable=True)
    ch.basic_publish(
        exchange='',
        routing_key='whatsapp_campaign',
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    conn.close()