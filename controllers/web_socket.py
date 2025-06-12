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
from services import customer_service, message_service
from schemas.CustomerSchema import CustomerCreate
from schemas.MessageSchema import MessageCreate
router = APIRouter()

# Store connected WebSocket clients
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# WebSocket endpoint
@router.websocket("/channel")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keeping connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Webhook endpoint
# @router.post("/webhook")
# async def webhook_receiver(request: Request):
#     body = await request.json()
#     await manager.broadcast(body)
#     return JSONResponse(content={"status": "broadcasted", "data": body})

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
        body_text = message[message_type]["body"] if "body" in message[message_type] else ""

        from_wa_id = message["from"]
        to_wa_id = value["metadata"]["display_phone_number"]
        timestamp = datetime.fromtimestamp(int(message["timestamp"]))

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

        # Optionally broadcast to websocket
        await manager.broadcast({
            "from":new_msg.from_wa_id,
            "to":new_msg.to_wa_id,
            "message":new_msg.body,
            "timestamp":new_msg.timestamp.isoformat(),
        })

        return {"status": "success", "message_id": new_msg.message_id}

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