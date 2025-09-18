from datetime import datetime, timedelta
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List
import re
import mimetypes
import mimetypes
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
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url, get_media_url
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url, get_media_url
from utils.razorpay_utils import create_razorpay_payment_link
from utils.ws_manager import manager
from utils.shopify_admin import update_variant_price
from utils.address_validator import analyze_address, format_errors_for_user

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

def _upload_header_image(access_token: str, image_path_or_url: str, phone_id: str) -> str:
    try:
        content = None
        filename = None
        content_type = None

        # Local file path
        if os.path.isfile(image_path_or_url):
            filename = os.path.basename(image_path_or_url)
            content_type = mimetypes.guess_type(image_path_or_url)[0] or "image/jpeg"
            with open(image_path_or_url, "rb") as f:
                content = f.read()
        else:
            # Assume URL
            resp = requests.get(image_path_or_url, timeout=15)
            if resp.status_code != 200:
                return None
            content = resp.content
            filename = os.path.basename(image_path_or_url.split("?")[0]) or "welcome.jpg"
            content_type = resp.headers.get("Content-Type") or mimetypes.guess_type(image_path_or_url)[0] or "image/jpeg"

        files = {
            "file": (filename, content, content_type),
            "messaging_product": (None, "whatsapp")
        }
        up = requests.post(get_media_url(phone_id), headers={"Authorization": f"Bearer {access_token}"}, files=files, timeout=20)
        if up.status_code == 200:
            return up.json().get("id")
    except Exception:
        return None
    return None

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

        # Fetch or create customer
        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Check prior messages
        prior_messages = message_service.get_messages_by_wa_id(db, wa_id)

        # 1️⃣ Onboarding prompt (only for first message)
        # if len(prior_messages) == 0:
        #     await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)

        # 2️⃣ Check if this looks like an address attempt
        is_address_candidate = message_type == "text" and len(body_text) > 30 and any(
            kw in body_text for kw in [
                "Full Name:", "House No.", "HouseStreet:", "Locality:", "City:", "State:", "Pincode:", "Phone:", "Phone Number:"
            ]
        )

        if message_type == "text" and is_address_candidate:
            try:
                parsed, addr_errors, _ = analyze_address(body_text)
                looks_like_address = any([
                    parsed.get("Pincode"), parsed.get("City"), parsed.get("State"),
                    parsed.get("HouseStreet"), parsed.get("Locality")
                ])
                if looks_like_address:
                    if addr_errors:
                        # Save user's address attempt to database
                        user_address_msg = MessageCreate(
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            type="text",
                            body=body_text,
                            timestamp=timestamp,
                            customer_id=customer.id,
                        )
                        message_service.create_message(db, user_address_msg)
                        
                        # Broadcast the user's address attempt
                        await manager.broadcast({
                            "from": from_wa_id,
                            "to": to_wa_id,
                            "type": "text",
                            "message": body_text,
                            "timestamp": timestamp.isoformat()
                        })
                        
                        # Send validation error to user (this also saves to DB)
                        error_text = format_errors_for_user(addr_errors)
                        await send_message_to_waid(wa_id, error_text, db)
                        
                        # Broadcast the error message to frontend (already saved by send_message_to_waid)
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": from_wa_id,
                            "type": "text",
                            "message": error_text,
                            "timestamp": datetime.now().isoformat()
                        })
                        return {"status": "validation_failed", "message_id": message_id}
                    else:
                        # Save address
                        customer_service.update_customer_address(db, customer.id, body_text)
                        message_data = MessageCreate(
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            type="text",
                            body=body_text,
                            timestamp=datetime.now(),
                            customer_id=customer.id,
                        )
                        new_msg = message_service.create_message(db, message_data)

                        await manager.broadcast({
                            "from": from_wa_id,
                            "to": to_wa_id,
                            "type": "text",
                            "message": new_msg.body,
                            "timestamp": new_msg.timestamp.isoformat(),
                        })

                        await send_message_to_waid(wa_id, "✅ Your address has been saved successfully!", db)

                        # After saving address, send payment link
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

                            # --- Test override for Shopify tracking flow ---
                            try:
                                # Default ON: freeze totals for test unless explicitly disabled
                                if os.getenv("TEST_SHOPIFY_TRACKING", "true").lower() in {"1", "true", "yes"}:
                                    test_price = int(os.getenv("TEST_CHECKOUT_PRICE_INR", "1"))
                                    test_shipping = int(os.getenv("TEST_SHIPPING_FEE_INR", "0"))
                                    total_amount = test_price + test_shipping

                                    # Optional: update a specific Shopify variant to this test price
                                    variant_id = os.getenv("TEST_SHOPIFY_VARIANT_ID")
                                    if variant_id:
                                        ok = update_variant_price(variant_id, test_price)
                                        if not ok:
                                            print("Warning: Failed to update Shopify variant price for test")
                            except Exception:
                                pass

                            if total_amount > 0:
                                # Try proxy payment link first
                                pay_link = None
                                try:
                                    bearer_token = None
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
                                except Exception:
                                    bearer_token = None

                                bearer_token = bearer_token or os.getenv("RAZORPAY_PROXY_BEARER_TOKEN")
                                payment_api_url = os.getenv("RAZORPAY_PROXY_PAYMENT_URL", "https://payments.olivaclinic.com/api/payment")
                                center_name = os.getenv("OLIVA_CENTER_NAME", "Corporate Training Center")
                                center_id = os.getenv("OLIVA_CENTER_ID", "90e79e59-6202-4feb-a64f-b647801469e4")

                                if bearer_token:
                                    payload = {
                                        "customer_name": customer.name or "Customer",
                                        "phone_number": customer.wa_id,
                                        "email": customer.email or "",
                                        "amount": int(round(total_amount)),
                                        "center": center_name,
                                        "center_id": center_id,
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
                                    except Exception:
                                        pay_link = None

                                if pay_link:
                                    await send_message_to_waid(wa_id, f"💳 Please complete your payment using this link: {pay_link}", db)
                                else:
                                    print("Auto payment link send skipped: no link generated")
                            else:
                                print("No latest order or zero amount; skipping auto payment link send")
                        except Exception as pay_err:
                            print("Auto payment link send error:", pay_err)

                        return {"status": "success", "message_id": message_id}

            except Exception as e:
                print("Address processing error:", e)
                await send_message_to_waid(wa_id, "❌ Failed to process your address. Please try again.", db)
                return {"status": "failed", "message_id": message_id}

        # 3️⃣ Regular text messages (non-address)
        if message_type == "text":
            inbound_text_msg = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="text",
                body=body_text,
                timestamp=timestamp,
                customer_id=customer.id
            )
            message_service.create_message(db, inbound_text_msg)
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "text",
                "message": body_text,
                "timestamp": timestamp.isoformat()
            })

        # 4️⃣ Hi/Hello auto-template
        raw = (body_text or "").strip()
        normalized = re.sub(r"[^a-z]", "", raw.lower())
        if message_type == "text" and (normalized in {"hi", "hello", "hlo"} or ("hi" in normalized or "hello" in normalized)):
            # call your existing welcome template sending logic here
            token_entry = get_latest_token(db)
            if token_entry and token_entry.token:
                try:
                    access_token = token_entry.token
                    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                    # Resolve media_id: prefer env; else use last inbound image from this user; fallback to provided ID
                    media_id = os.getenv("WELCOME_TEMPLATE_MEDIA_ID") or "2185668755244609"
                    if not media_id:
                        try:
                            last_images = [m for m in reversed(prior_messages) if m.type == "image" and m.media_id]
                            if last_images:
                                media_id = last_images[0].media_id
                        except Exception:
                            media_id = None

                    components = []
                    if media_id:
                        components.append({
                            "type": "header",
                            "parameters": [{"type": "image", "image": {"id": media_id}}]
                        })
                    components.append({
                        "type": "body",
                        "parameters": [{"type": "text", "text": sender_name}]
                    })

                    payload = {
                        "messaging_product": "whatsapp",
                        "to": wa_id,
                        "type": "template",
                        "template": {
                            "name": "welcome_msg",
                            "language": {"code": "en_US"},
                            **({"components": components} if components else {})
                        }
                    }

                    resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
                    if resp.status_code != 200:
                        print("Failed to send welcome template:", resp.text)
                    else:
                        try:
                            tpl_msg_id = resp.json()["messages"][0]["id"]
                            tpl_message = MessageCreate(
                                message_id=tpl_msg_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body=f"Welcome template sent to {sender_name}",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                                media_id=media_id if media_id else None
                            )
                            message_service.create_message(db, tpl_message)
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template",
                                "message": f"Welcome template sent to {sender_name}",
                                "timestamp": datetime.now().isoformat(),
                                **({"media_id": media_id} if media_id else {})
                            })
                        except Exception:
                            pass
                except Exception as _:
                    pass

        # Send onboarding prompt on very first message from this WA ID
        prior_messages = message_service.get_messages_by_wa_id(db, wa_id)
        if len(prior_messages) == 0:
            await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)
        # (prompt already sent above on very first message)

        # (single hi/hello trigger handled above; removed duplicate block)

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
            # try:
            #     total_amount = sum([p.get("item_price", 0) * p.get("quantity", 1) for p in order["product_items"]])
            #     payment_payload = PaymentCreate(order_id=order_obj.id, amount=float(total_amount), currency=order["product_items"][0].get("currency", "INR"))
            #     payment = payment_service.create_payment_link(db, payment_payload)
            #     if payment.razorpay_short_url:
            #         await send_message_to_waid(wa_id, f"💳 Please complete your payment of ₹{int(total_amount)} using this link: {payment.razorpay_short_url}", db)
            # except Exception as e:
            #     print("Payment link creation failed:", e)

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
        elif message_type == "button":
            # Template button reply (WhatsApp sets type = "button" for template quick replies)
            btn = message.get("button", {})
            btn_text = btn.get("text", "")
            btn_id = btn.get("payload") or btn.get("id") or ""

            reply_text = btn_text or btn_id or "[Button Reply]"
            msg_button = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="button",
                body=reply_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, msg_button)
            
            # Broadcast button click for frontend display
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "button",
                "message": f"🔘 {reply_text}",
                "timestamp": timestamp.isoformat(),
            })

            # If user tapped Buy Products on welcome template → send catalog link
            choice_text = (reply_text or "").lower()
            if ("buy" in choice_text) or ("product" in choice_text) or (btn_id and str(btn_id).lower() in {"buy_products", "buy", "products"}):
                try:
                    await send_message_to_waid(wa_id, "🛍️ Browse our catalog: https://wa.me/c/917729992376", db)
                except Exception:
                    pass

            return {"status": "success", "message_id": message_id}

        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            i_type = interactive.get("type")
            title = None
            reply_id = None
            try:
                if i_type == "button_reply":
                    title = interactive.get("button_reply", {}).get("title")
                    reply_id = interactive.get("button_reply", {}).get("id")
                elif i_type == "list_reply":
                    title = interactive.get("list_reply", {}).get("title")
                    reply_id = interactive.get("list_reply", {}).get("id")
            except Exception:
                title = None
                reply_id = None

            # Save user's interactive reply
            reply_text = title or reply_id or "[Interactive Reply]"
            msg_interactive = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="interactive",
                body=reply_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, msg_interactive)
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "interactive",
                "message": reply_text,
                "timestamp": timestamp.isoformat(),
            })

            # If user chose Buy Products → send only the WhatsApp catalog link
            choice_text = (reply_text or "").lower()
            if ("buy" in choice_text) or ("product" in choice_text) or (reply_id and reply_id.lower() in {"buy_products", "buy", "products"}):
                try:
                    await send_message_to_waid(wa_id, "🛍️ Browse our catalog: https://wa.me/c/917729992376", db)
                except Exception:
                    pass
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
        
        elif message_type != "text":
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
                "to": to_wa_id,
                "type": message_type,
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