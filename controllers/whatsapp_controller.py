from datetime import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from controllers.web_socket import manager
from schemas.CustomerSchema import CustomerCreate
from schemas.MessageSchema import MessageCreate
from schemas.WhatsappToken import WhatsAppTokenCreate
from database.db import get_db
from services import customer_service, message_service, whatsapp_service
from services.whatsapp_service import create_whatsapp_token

router = APIRouter(tags=["WhatsApp Token"])

@router.post("/token", status_code=201)
def add_token(token_data: WhatsAppTokenCreate, db: Session = Depends(get_db)):
    try:
        create_whatsapp_token(db, token_data)
        return {"status": "success", "message": "Token saved securely"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"

@router.post("/send-message")
async def send_whatsapp_message(
    wa_id: str,
    body: str,
    db: Session = Depends(get_db)
):
    try:
        # Step 1: Get token from DB
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise HTTPException(status_code=400, detail="Token not available")

        token = token_obj.token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Step 2: Send message via WhatsApp API
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body
            }
        }

        response = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to send message: {response.text}")

        customer_data = CustomerCreate(wa_id=wa_id, name="")  # name can be empty if unknown
        customer = customer_service.get_or_create_customer(db, customer_data)

        # Step 4: Save message as sent from business
        message_data = MessageCreate(
            message_id=response.json()["messages"][0]["id"],
            from_wa_id="917729992376",
            to_wa_id=wa_id,
            type="text",
            body=body,
            timestamp=datetime.now(),
            customer_id=customer.id
        )
        message = message_service.create_message(db, message_data)


        await manager.broadcast(
            {
                "from": message.from_wa_id,
                "to": message.to_wa_id,
                "message": message.body,
                "timestamp": message.timestamp.isoformat(),
            }
        )


        return {
            "status": "success",
            "message_id": message.message_id
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}