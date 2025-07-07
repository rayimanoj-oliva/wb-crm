from http.client import HTTPException

import requests

from services import whatsapp_service

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"
def send_message_to_waid(wa_id: str, message_body: str, db):
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

    # Send the POST request
    response = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)

    # Handle response
    if response.status_code == 200 or response.status_code == 201:
        return response.json()
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to send message: {response.text}"
        )