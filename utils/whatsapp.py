from datetime import datetime
from fastapi import HTTPException


import requests

from schemas.customer_schema import CustomerCreate
from sqlalchemy.orm import Session
from models.models import Category, SubCategory, Product
from config.constants import get_messages_url
import os
from schemas.message_schema import MessageCreate
from services import whatsapp_service, customer_service, message_service
from services.followup_service import schedule_next_followup
from utils.ws_manager import manager

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"

async def send_message_to_waid(wa_id: str, message_body: str, db, from_wa_id="917729992376", *, schedule_followup: bool = False, stage_label: str | None = None):
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

    # Schedule a follow-up for any outbound message unless explicitly disabled
    try:
        if schedule_followup:
            from services.followup_service import FOLLOW_UP_1_DELAY_MINUTES
            schedule_next_followup(db, customer_id=customer.id, delay_minutes=FOLLOW_UP_1_DELAY_MINUTES, stage_label=stage_label)
    except Exception:
        pass
    
    # Debug: Print message details to verify saving
    print(f"[send_message_to_waid] DEBUG - Outbound message saved:")
    print(f"  - Message ID: {new_msg.message_id}")
    print(f"  - From: {new_msg.from_wa_id}")
    print(f"  - To: {new_msg.to_wa_id}")
    print(f"  - Type: {new_msg.type}")
    print(f"  - Body: {new_msg.body}")
    print(f"  - Timestamp: {new_msg.timestamp}")
    print(f"  - Customer ID: {new_msg.customer_id}")

    await manager.broadcast({
        "from": new_msg.from_wa_id,
        "to": new_msg.to_wa_id,
        "type": "text",
        "message": new_msg.body,
        "timestamp": new_msg.timestamp.isoformat(),
    })

    return new_msg


def _get_headers(db):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")
    return {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }


async def send_category_list(wa_id: str, db: Session):
    headers = _get_headers(db)
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    categories = db.query(Category).all()
    rows = []
    for c in categories:
        rows.append({
            "id": str(c.id),
            "title": c.name[:24],
            "description": (c.description or "")[:72]
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Browse Categories"},
            "body": {"text": "Choose a category"},
            "action": {
                "button": "Choose",
                "sections": [{
                    "title": "Categories",
                    "rows": rows or [{"id": "noop", "title": "No categories", "description": "Add from admin"}]
                }]
            }
        }
    }
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send categories: {res.text}")


async def send_subcategory_list(wa_id: str, category_id: str, db: Session):
    headers = _get_headers(db)
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    subs = db.query(SubCategory).filter(SubCategory.category_id == category_id).all()
    rows = []
    for s in subs:
        rows.append({
            "id": str(s.id),
            "title": s.name[:24],
            "description": (s.description or "")[:72]
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Subcategories"},
            "body": {"text": "Choose a subcategory"},
            "action": {
                "button": "Choose",
                "sections": [{
                    "title": "Subcategories",
                    "rows": rows or [{"id": f"cat:{category_id}", "title": "All items", "description": "No subcategories"}]
                }]
            }
        }
    }
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send subcategories: {res.text}")


async def send_products_list(wa_id: str, category_id: str = None, subcategory_id: str = None, db: Session = None):
    headers = _get_headers(db)
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    q = db.query(Product)
    if subcategory_id:
        q = q.filter(Product.sub_category_id == subcategory_id)
    elif category_id:
        q = q.filter(Product.category_id == category_id)
    products = q.limit(10).all()
    rows = []
    for p in products:
        rows.append({
            "id": str(p.id),
            "title": p.name[:24],
            "description": f"₹{int(p.price)} | Stock: {p.stock}"
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Products"},
            "body": {"text": "Pick a product"},
            "action": {
                "button": "Choose",
                "sections": [{"title": "Products", "rows": rows or [{"id": "noop", "title": "No products available"}]}]
            }
        }
    }
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send products: {res.text}")

async def send_location_to_waid(wa_id: str, latitude: float, longitude: float, name: str, address: str, db, from_wa_id="917729992376"):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    headers = {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }

    location_data = {
        "latitude": latitude,
        "longitude": longitude,
    }
    if name:
        location_data["name"] = name
    if address:
        location_data["address"] = address

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "location",
        "location": location_data
    }

    res = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send location message: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    location_body = ", ".join(filter(None, [name, address]))

    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="location",
        body=location_body,
        timestamp=datetime.now(),
        customer_id=customer.id,
        latitude=latitude,
        longitude=longitude,
    )
    new_msg = message_service.create_message(db, message_data)

    broadcast_data = {
        "from": new_msg.from_wa_id,
        "to": new_msg.to_wa_id,
        "type": "location",
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": new_msg.timestamp.isoformat(),
    }
    if name:
        broadcast_data["name"] = name
    if address:
        broadcast_data["address"] = address

    await manager.broadcast(broadcast_data)

    return new_msg