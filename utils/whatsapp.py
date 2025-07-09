from datetime import datetime
from http.client import HTTPException

import requests

from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from services import whatsapp_service, customer_service, message_service

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"
async def send_message_to_waid(wa_id: str, message_body: str,db):
    # Get the token
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    # Create headers
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Create the message payload
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {
            "body": message_body
        }
    }

    res = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {res.text}")
    message_id = res.json()["messages"][0]["id"]
    customer_data = CustomerCreate(wa_id=wa_id, name="")
    customer = customer_service.get_or_create_customer(db, customer_data)

    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id="917729992376",
        to_wa_id=wa_id,
        type="text",
        body=message_body or "",
        timestamp=datetime.now(),
        customer_id=customer.id,

    )
    new_msg = message_service.create_message(db, message_data)

    return new_msg