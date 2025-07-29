from datetime import datetime
from http.client import HTTPException

import requests

from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from services import whatsapp_service, customer_service, message_service
from utils.ws_manager import manager

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"

async def send_message_to_waid(wa_id: str, message_body: str, db, from_wa_id="917729992376"):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    headers = {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": { "body": message_body }
    }

    res = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="text",
        body=message_body,
        timestamp=datetime.now(),
        customer_id=customer.id,
    )
    new_msg = message_service.create_message(db, message_data)

    await manager.broadcast({
        "from": new_msg.from_wa_id,
        "to": new_msg.to_wa_id,
        "type": "text",
        "message": new_msg.body,
        "timestamp": new_msg.timestamp.isoformat(),
    })

    return new_msg

async def send_welcome_template_to_waid(wa_id: str, customer_name: str, db, from_wa_id="917729992376"):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    headers = {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "template",
        "template": {
            "name": "welcome_msg",
            "language": {
                "code": "en"
            },
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {
                                "link": "https://scontent.whatsapp.net/v/t61.29466-34/506841557_711768841552344_4400215025584897919_n.png?ccb=1-7&_nc_sid=8b1bef&_nc_ohc=E0X6MAQr6_YQ7kNvwGh3H2n&_nc_oc=Adk7ZP_5xtRfnoxTFYzj5-uWkaPdjrNJlTngPnYevt0ZwKz5ROzO7iLNGxX4RLMHLFY&_nc_zt=3&_nc_ht=scontent.whatsapp.net&edm=AH51TzQEAAAA&_nc_gid=Vpzwj8gpWlgZh3qhSmaqsg&oh=01_Q5Aa2AExUhdaeVR1cX85B0ICsAMDM7urN4ceMZdXRTWmYuULGA&oe=68B060AC"
                            }
                        }
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": customer_name
                        }
                    ]
                }
            ]
        }
    }

    res = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
    print(res.json())
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send welcome template: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=customer_name))

    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="template",
        body=f"Welcome template sent to {customer_name}",
        timestamp=datetime.now(),
        customer_id=customer.id,
    )
    new_msg = message_service.create_message(db, message_data)

    await manager.broadcast({
        "from": new_msg.from_wa_id,
        "to": new_msg.to_wa_id,
        "type": "template",
        "message": new_msg.body,
        "timestamp": new_msg.timestamp.isoformat(),
    })

    return res.json()
