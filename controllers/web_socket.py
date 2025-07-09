from datetime import datetime
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List
import asyncio

from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from schemas.orders_schema import OrderItemCreate,OrderCreate
from services import customer_service, message_service, order_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager

router = APIRouter()


# WebSocket endpoint
@router.websocket("/channel")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keeping connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

VERIFY_TOKEN = "Oliva@123"

@router.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):

    try:
        body = await request.json()

        entry = body["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        contact = value["contacts"][0]
        message = value["messages"][0]

        # Extract customer info
        wa_id = contact["wa_id"]
        sender_name = contact["profile"]["name"]

        # Create or fetch customer
        customer_data = CustomerCreate(wa_id=wa_id, name=sender_name)
        customer = customer_service.get_or_create_customer(db, customer_data)

        # Extract message info
        message_id = message["id"]
        message_type = message["type"]

        from_wa_id = message["from"]
        to_wa_id = value["metadata"]["display_phone_number"]
        timestamp = datetime.fromtimestamp(int(message["timestamp"]))

        print(from_wa_id, to_wa_id)
        if message_type == "order":


            order = message["order"]
            catalog_id = order["catalog_id"]
            products = order["product_items"]

            order_items = [
                OrderItemCreate(
                    product_retailer_id=prod["product_retailer_id"],
                    quantity=prod["quantity"],
                    item_price=prod["item_price"],
                    currency=prod["currency"]
                ) for prod in products
            ]

            order_data = OrderCreate(
                customer_id=customer.id,
                catalog_id=catalog_id,
                timestamp=timestamp,
                items=order_items
            )
            new_order = order_service.create_order(db, order_data)

            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "order",
                "catalog_id": catalog_id,
                "products": products,
                "timestamp": timestamp.isoformat(),
            })
            await send_message_to_waid(from_wa_id,"📌 Please enter your full delivery address in the format below:",db)
            await send_message_to_waid(from_wa_id,
                                 """
Full Name:  

House No. + Street:  

Area / Locality:  

City:  

State:  

Pincode:  

Landmark (Optional):  

Phone Number:

                                 """,db)
        else:
            body_text = message[message_type]["body"] if "body" in message[message_type] else ""

            # Simple heuristic to detect address message
            if any(keyword in body_text for keyword in
                   ["Full Name:", "House No.", "Pincode:", "Phone Number:"]) and len(body_text) > 30:

                try:
                    customer_service.update_customer_address(db, customer.id, body_text)
                    message_data = MessageCreate(
                        message_id=message_id,
                        from_wa_id="917729992376",
                        to_wa_id=wa_id,
                        type="text",
                        body=body_text or "",
                        timestamp=datetime.now(),
                        customer_id=customer.id,

                    )
                    new_msg = message_service.create_message(db, message_data)
                    await manager.broadcast({
                        "from": new_msg.to_wa_id,
                        "to": new_msg.from_wa_id,
                        "type": "text",
                        "message": new_msg.body,
                        "timestamp": new_msg.timestamp.isoformat(),
                    })
                    new_msg = await send_message_to_waid(from_wa_id, "✅ Your address has been saved successfully!", db)
                except Exception as e:
                    print("Address save error:", e)
                    new_msg = await send_message_to_waid(from_wa_id, "❌ Failed to save your address. Please try again.", db)
            else:
                # Save message
                message_data = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type=message_type,
                    body=body_text,
                    timestamp=timestamp,
                    customer_id=customer.id
                )
                new_msg = message_service.create_message(db, message_data)

        return {"status": "success", "message_id": message_id}

    except Exception as e:
        print("Webhook error:", e)
        return {"status": "failed", "error": str(e)}

@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        # implement the database insertion logic here and complete this function
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403)