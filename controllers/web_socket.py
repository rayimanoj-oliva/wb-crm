from datetime import datetime
from http.client import HTTPException

import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List # This import might not be strictly needed based on the current code
import asyncio

from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from schemas.orders_schema import OrderItemCreate,OrderCreate
from services import customer_service, message_service, order_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid, send_welcome_template_to_waid
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
        print("✅ Webhook payload received:", body) # Added print for clarity

        value = body["entry"][0]["changes"][0]["value"]
        contact = value["contacts"][0]
        message = value["messages"][0]

        wa_id = contact["wa_id"]
        sender_name = contact["profile"]["name"]
        from_wa_id = message["from"]
        to_wa_id = value["metadata"]["display_phone_number"]
        timestamp = datetime.fromtimestamp(int(message["timestamp"]))
        message_type = message["type"]
        message_id = message["id"]
        body_text = message[message_type].get("body", "")
        # ✅ If the message is exactly "hi" (case-insensitive), send welcome template always
        if body_text.strip().lower() == "hi":
            try:
                await send_welcome_template_to_waid(wa_id=wa_id, customer_name=sender_name, db=db)
                print(f"✅ Sent welcome template to {sender_name} ({wa_id}) on 'hi'")
            except Exception as e:
                print(f"❌ Failed to send welcome template on 'hi':", e)

        is_address = any(
            keyword in body_text for keyword in ["Full Name:", "House No.", "Pincode:", "Phone Number:"]) and len(
            body_text) > 30

        # --- IMPORTANT CHANGE HERE ---
        # customer_service.get_or_create_customer must return (customer_object, boolean_created)
        customer, created = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Only send welcome template if the customer is newly created (first message from them)
        if created:
            print(f"🎉 New customer detected: {sender_name} ({wa_id}). Sending welcome template.")
            await send_welcome_template_to_waid(wa_id=wa_id, customer_name=sender_name, db=db)
        else:
            print(f"Returning customer: {sender_name} ({wa_id}). No welcome template sent.")


        if message_type == "order":
            order = message["order"]
            order_items = [
                OrderItemCreate(
                    product_retailer_id=prod["product_retailer_id"],
                    quantity=prod["quantity"],
                    item_price=prod["item_price"],
                    currency=prod["currency"]
                ) for prod in order["product_items"]
            ]
            order_data = OrderCreate(
                customer_id=customer.id,
                catalog_id=order["catalog_id"],
                timestamp=timestamp,
                items=order_items
            )
            order_service.create_order(db, order_data)

            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "order",
                "catalog_id": order["catalog_id"],
                "products": order["product_items"],
                "timestamp": timestamp.isoformat(),
            })

            await send_message_to_waid(wa_id, "📌 Please enter your full delivery address in the format below:", db)
            await send_message_to_waid(wa_id,
                """
Full Name:

House No. + Street:

Area / Locality:

City:

State:

Pincode:

Landmark (Optional):

Phone Number:
                """, db)

        elif is_address:
                try:
                    customer_service.update_customer_address(db, customer.id, body_text)
                    message_data = MessageCreate(
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id="917729992376", # Your business WA ID
                        type="text",
                        body=body_text,
                        timestamp=datetime.now(),
                        customer_id=customer.id,
                    )
                    new_msg = message_service.create_message(db, message_data)

                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": "917729992376", # Your business WA ID
                        "type": "text",
                        "message": new_msg.body,
                        "timestamp": new_msg.timestamp.isoformat(),
                    })

                    await send_message_to_waid(wa_id, "✅ Your address has been saved successfully!", db)
                except Exception as e:
                    print("Address save error:", e)
                    await send_message_to_waid(wa_id, "❌ Failed to save your address. Please try again.", db)
        else:
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type=message_type,
                body=body_text,
                timestamp=timestamp,
                customer_id=customer.id
            )
            message_service.create_message(db, message_data)
            await manager.broadcast({
                "from": from_wa_id,
                "to": "917729992376", # Your business WA ID
                "type": "text",
                "message": message_data.body,
                "timestamp": message_data.timestamp.isoformat()
            })

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