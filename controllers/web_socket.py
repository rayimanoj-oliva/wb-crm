from datetime import datetime, timedelta
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List
import asyncio
import os
import requests

from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from schemas.orders_schema import OrderItemCreate,OrderCreate, PaymentCreate
from services import customer_service, message_service, order_service
from services import payment_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid
from utils.razorpay_utils import create_razorpay_payment_link
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
        is_address = any(
            keyword in body_text for keyword in ["Full Name:", "House No.", "Pincode:", "Phone Number:"]) and len(
            body_text) > 30

        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Auto-send welcome template if user said "hi"/"hello"/"hlo" and hasn't received one recently
        # if body_text.lower() in ["hi", "hello", "hlo"]:
        #     await send_welcome_template_to_waid(wa_id=from_wa_id, customer_name=sender_name, db=db)
        #     await manager.broadcast({
        #         "from": "system",
        #         "to": from_wa_id,
        #         "type": "template",
        #         "message": "Welcome template sent",
        #         "timestamp": datetime.now().isoformat()
        #     })
        #
        #
        # # result = await send_welcome_template_to_waid(wa_id=from_wa_id, customer_name=sender_name, db=db)
        # # return result

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
            order_obj = order_service.create_order(db, order_data)

            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "order",
                "catalog_id": order["catalog_id"],
                "products": order["product_items"],
                "timestamp": timestamp.isoformat(),
            })

            # Create Razorpay payment link for the order total
            try:
                total_amount = sum([p.get("item_price", 0) * p.get("quantity", 1) for p in order["product_items"]])
                payment_payload = PaymentCreate(order_id=order_obj.id, amount=float(total_amount), currency=order["product_items"][0].get("currency", "INR"))
                payment = payment_service.create_payment_link(db, payment_payload)
                if payment.razorpay_short_url:
                    await send_message_to_waid(wa_id, f"💳 Please complete your payment of ₹{int(total_amount)} using this link: {payment.razorpay_short_url}", db)
            except Exception as e:
                print("Payment link creation failed:", e)

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
        elif message_type == "location":
            location = message["location"]
            location_name = location.get("name", "")
            location_address = location.get("address", "")

            # convert to float safely
            latitude = float(location["latitude"]) if "latitude" in location else None
            longitude = float(location["longitude"]) if "longitude" in location else None

            # body fallback
            if location_name or location_address:
                location_body = ", ".join(filter(None, [location_name, location_address]))
            else:
                location_body = f"Shared Location - Lat: {latitude}, Lng: {longitude}"

            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="location",
                body=location_body,
                timestamp=timestamp,
                customer_id=customer.id,
                latitude=latitude,
                longitude=longitude,
            )
            message_service.create_message(db, message_data)

            broadcast_payload = {
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "location",
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp.isoformat()
            }

            if location_name:
                broadcast_payload["name"] = location_name
            if location_address:
                broadcast_payload["address"] = location_address

            await manager.broadcast(broadcast_payload)

            return {"status": "success", "message_id": message_id}

        elif message_type == "image":
            image = message["image"]

            media_id = image.get("id")
            caption = image.get("caption", "")
            mime_type = image.get("mime_type", "")
            filename = image.get("filename", "")

            # Save message in DB
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="image",
                body=caption or "[Image]",
                timestamp=timestamp,
                customer_id=customer.id,
                media_id=media_id,
                caption=caption,
                filename=filename,
                mime_type=mime_type,
            )
            new_msg = message_service.create_message(db, message_data)

            # Broadcast to WebSocket clients
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "image",
                "media_id": media_id,
                "caption": caption,
                "filename": filename,
                "mime_type": mime_type,
                "timestamp": timestamp.isoformat(),
            })

            return {"status": "success", "message_id": message_id}
        elif message_type == "document":
            document = message["document"]

            media_id = document.get("id")
            caption = document.get("caption", "")
            mime_type = document.get("mime_type", "")
            filename = document.get("filename", "")

            # Save document message in DB
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="document",
                body=caption or "[Document]",
                timestamp=timestamp,
                customer_id=customer.id,
                media_id=media_id,
                caption=caption,
                filename=filename,
                mime_type=mime_type,
            )
            new_msg = message_service.create_message(db, message_data)

            # Broadcast to WebSocket clients
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "document",
                "media_id": media_id,
                "caption": caption,
                "filename": filename,
                "mime_type": mime_type,
                "timestamp": timestamp.isoformat(),
            })

            return {"status": "success", "message_id": message_id}
        
        elif is_address:
                try:
                    customer_service.update_customer_address(db, customer.id, body_text)
                    message_data = MessageCreate(
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id="917729992376",
                        type="text",
                        body=body_text,
                        timestamp=datetime.now(),
                        customer_id=customer.id,
                    )
                    new_msg = message_service.create_message(db, message_data)

                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": "917729992376",
                        "type": "text",
                        "message": new_msg.body,
                        "timestamp": new_msg.timestamp.isoformat(),
                    })

                    await send_message_to_waid(wa_id, "✅ Your address has been saved successfully!", db)

                    # --- After address saved: create payment link via proxy and send automatically ---
                    try:
                        # Compute order total for this customer (latest order)
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        total_amount = 0
                        if latest_order:
                            for item in latest_order.items:
                                qty = item.quantity or 1
                                price = item.item_price or item.price or 0
                                total_amount += float(price) * int(qty)

                        if total_amount > 0:
                            # Obtain bearer token dynamically if possible; fallback to static env
                            bearer_token = None
                            try:
                                token_url = os.getenv("RAZORPAY_TOKEN_URL", "https://payments.olivaclinic.com/api/token")
                                username = os.getenv("RAZORPAY_USERNAME") or os.getenv("RAZORPAY_PROXY_USERNAME")
                                password = os.getenv("RAZORPAY_PASSWORD") or os.getenv("RAZORPAY_PROXY_PASSWORD")
                                if username and password:
                                    token_headers = {
                                        "Accept": "application/json",
                                        "Content-Type": "application/x-www-form-urlencoded",
                                    }
                                    token_data = {
                                        "username": username,
                                        "password": password,
                                    }
                                    token_resp = requests.post(token_url, data=token_data, headers=token_headers, timeout=15)
                                    if token_resp.status_code == 200:
                                        bearer_token = token_resp.json().get("access_token")
                            except Exception as _:
                                bearer_token = None
                            # Final fallback to static token
                            bearer_token = bearer_token or os.getenv("RAZORPAY_PROXY_BEARER_TOKEN")
                            payment_api_url = os.getenv("RAZORPAY_PROXY_PAYMENT_URL", "https://payments.olivaclinic.com/api/payment")
                            center_name = os.getenv("OLIVA_CENTER_NAME", "Corporate Training Center")
                            center_id = os.getenv("OLIVA_CENTER_ID", "90e79e59-6202-4feb-a64f-b647801469e4")

                            pay_link = None
                            if bearer_token:
                                payload = {
                                    "customer_name": customer.name or "Customer",
                                    "phone_number": customer.wa_id,
                                    "email": customer.email or "",
                                    "amount": int(round(total_amount)),
                                    "center": center_name,
                                    "center_id": center_id,
                                    # minimal required personal/address fields
                                    "personal_info_first_name": (customer.name or "").split(" ")[0] if (customer.name) else "",
                                    "personal_info_last_name": "",
                                    "personal_info_mobile_country_code": 91,
                                    "personal_info_mobile_number": customer.wa_id,
                                    "address_info_country_id": 95,
                                    "address_info_state_id": -2,
                                    "preferences_receive_transactional_email": True,
                                    "preferences_receive_transactional_sms": True,
                                    "preferences_receive_marketing_email": True,
                                    "preferences_receive_marketing_sms": True,
                                    "preferences_recieve_lp_stmt": True,
                                }

                                headers = {
                                    "Authorization": f"Bearer {bearer_token}",
                                    "Content-Type": "application/json",
                                    "Accept": "application/json, text/plain, */*",
                                }
                                resp = requests.post(payment_api_url, json=payload, headers=headers, timeout=20)
                                if resp.status_code == 200:
                                    resp_json = resp.json()
                                    pay_link = resp_json.get("payment_link")
                                else:
                                    print("Payment link creation via proxy failed:", resp.text)

                            # Fallback to direct Razorpay link if proxy not available or failed
                            if not pay_link:
                                try:
                                    direct_resp = create_razorpay_payment_link(
                                        amount=float(total_amount),
                                        currency="INR",
                                        description=f"WA Order {str(latest_order.id) if latest_order else ''}"
                                    )
                                    pay_link = direct_resp.get("short_url") if isinstance(direct_resp, dict) else None
                                except Exception as _:
                                    pay_link = None

                            if pay_link:
                                await send_message_to_waid(wa_id, f"💳 Please complete your payment using this link: {pay_link}", db)
                            else:
                                print("Auto payment link send skipped: no link generated")
                        else:
                            print("No latest order or zero amount; skipping auto payment link send")
                    except Exception as pay_err:
                        print("Auto payment link send error:", pay_err)
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
                "to": "917729992376",
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