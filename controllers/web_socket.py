from datetime import datetime, timedelta
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List
import re
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
from utils.razorpay_utils import create_razorpay_payment_link
from utils.ws_manager import manager
from utils.shopify_admin import update_variant_price
from utils.address_validator import analyze_address, format_errors_for_user

router = APIRouter()


# In-memory store: { wa_id: True/False }
awaiting_address_users = {}


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

async def send_address_form(wa_id: str, db: Session):
    """Send structured address collection form similar to JioMart"""
    try:
        # Get WhatsApp token
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address form. Please try again.", db)
            return
        
        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
        
        # Create interactive form for address collection (using buttons as fallback)
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "📍 New Address"
                },
                "body": {
                    "text": "Please choose how you'd like to add your address:"
                },
                "footer": {
                    "text": "All fields are required for delivery"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "fill_form_step1",
                                "title": "📝 Fill Address Form"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "share_location",
                                "title": "📍 Share Location"
                            }
                        }
                    ]
                }
            }
        }
        
        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                form_msg_id = resp.json()["messages"][0]["id"]
                form_message = MessageCreate(
                    message_id=form_msg_id,
                    from_wa_id="917729992376",  # Your WhatsApp number
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Address collection form sent",
                    timestamp=datetime.now(),
                    customer_id=customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="")).id
                )
                message_service.create_message(db, form_message)
                
                await manager.broadcast({
                    "from": "917729992376",
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address collection form sent",
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                print(f"Error saving address form message: {e}")
        else:
            print(f"Failed to send address form: {resp.text}")
            # Fallback to simple text form
            await send_message_to_waid(wa_id, "📝 Please enter your address in this format:", db)
            await send_message_to_waid(wa_id, 
                """*Contact Details:*
Full Name: [Your Name]
Phone: [10-digit number]

*Address Details:*
Pincode: [6-digit pincode]
House No. & Street: [House number and street]
Area/Locality: [Your area]
City: [Your city]
State: [Your state]
Landmark: [Optional - nearby landmark]""", db)
            
    except Exception as e:
        print(f"Error sending address form: {e}")
        # Fallback to simple text form
        await send_message_to_waid(wa_id, "📝 Please enter your address in this format:", db)
        await send_message_to_waid(wa_id, 
            """*Contact Details:*
Full Name: [Your Name]
Phone: [10-digit number]

*Address Details:*
Pincode: [6-digit pincode]
House No. & Street: [House number and street]
Area/Locality: [Your area]
City: [Your city]
State: [Your state]
Landmark: [Optional - nearby landmark]""", db)


async def send_address_flow_button(wa_id: str, db: Session, customer_name: str = "Customer"):
    """Send WhatsApp Flow button for address collection"""
    try:
        # Get WhatsApp token
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send address flow. Please try again.", db)
            return
        
        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
        
        # Import the flow template
        from utils.address_templates import get_address_collection_flow_template
        
        # Get the flow payload
        payload = get_address_collection_flow_template(wa_id, customer_name)
        
        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                flow_msg_id = resp.json()["messages"][0]["id"]
                flow_message = MessageCreate(
                    message_id=flow_msg_id,
                    from_wa_id="917729992376",  # Your WhatsApp number
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Address collection flow sent",
                    timestamp=datetime.now(),
                    customer_id=customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name="")).id
                )
                message_service.create_message(db, flow_message)
                
                await manager.broadcast({
                    "from": "917729992376",
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Address collection flow sent",
                    "timestamp": datetime.now().isoformat()
                })
                
                print(f"Address flow button sent successfully: {flow_msg_id}")
                
            except Exception as e:
                print(f"Error saving address flow message: {e}")
        else:
            print(f"Failed to send address flow: {resp.text}")
            # Fallback to regular form
            await send_address_form(wa_id, db)
            
    except Exception as e:
        print(f"Error sending address flow: {e}")
        # Fallback to regular form
        await send_address_form(wa_id, db)


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

        # 2️⃣ ADDRESS COLLECTION - Only through structured form
        if awaiting_address_users.get(wa_id, False):
            # User is in address collection flow, but should use the structured form
            await send_message_to_waid(wa_id, "📍 Please use the address form above to enter your details. Click the '📝 Fill Address Form' button.", db)
            return {"status": "awaiting_address_form", "message_id": message_id}

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

            # NEW ADDRESS COLLECTION SYSTEM - Send "collect_address" template from Meta
            try:
                # Calculate order total
                total_amount = sum([p.get("item_price", 0) * p.get("quantity", 1) for p in order["product_items"]])
                
                # Get WhatsApp token
                token_entry = get_latest_token(db)
                if token_entry and token_entry.token:
                    access_token = token_entry.token
                    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                    
                    # Send collect_address template from Meta (no parameters)
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": wa_id,
                        "type": "template",
                        "template": {
                            "name": "collect_address",
                            "language": {"code": "en_US"}
                        }
                    }
                    
                    resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
                    if resp.status_code == 200:
                        try:
                            tpl_msg_id = resp.json()["messages"][0]["id"]
                            tpl_message = MessageCreate(
                                message_id=tpl_msg_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="template",
                                body=f"Address collection template sent to {customer.name or 'Customer'}",
                                timestamp=datetime.now(),
                                customer_id=customer.id
                            )
                            message_service.create_message(db, tpl_message)
                            
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template",
                                "message": f"Address collection template sent to {customer.name or 'Customer'}",
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            # Mark user as awaiting address for button responses
                            awaiting_address_users[wa_id] = True
                            
                        except Exception as e:
                            print(f"Error saving collect_address template message: {e}")
                    else:
                        print(f"Failed to send collect_address template: {resp.text}")
                        # Fallback to structured form
                        await send_address_form(wa_id, db)
                else:
                    print("No WhatsApp token available for collect_address template")
                    # Fallback to structured form
                    await send_address_form(wa_id, db)
                    
            except Exception as e:
                print(f"Error sending collect_address template: {e}")
                # Fallback to structured form
                await send_address_form(wa_id, db)
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

            # NEW: Check if this is part of address collection
            try:
                from services.address_collection_service import AddressCollectionService
                address_service = AddressCollectionService(db)
                result = await address_service.handle_location_message(
                    wa_id=wa_id,
                    latitude=latitude,
                    longitude=longitude,
                    location_name=location_name,
                    location_address=location_address
                )
                
                if result["success"]:
                    # Address collection handled successfully
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
                    
                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": to_wa_id,
                        "type": "location",
                        "latitude": latitude,
                        "longitude": longitude,
                        "timestamp": timestamp.isoformat(),
                    })
                    return {"status": "address_collected", "message_id": message_id}
                else:
                    # Fallback to old location handling
                    pass
            except Exception as e:
                print(f"Address collection location handling failed: {e}")
                # Fallback to old location handling

            # OLD LOCATION HANDLING (fallback)
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
            
            # Broadcast button click as a text message for frontend display
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "text",
                "message": f"🔘 {reply_text}",
                "timestamp": timestamp.isoformat(),
            })

            # Handle different button types
            choice_text = (reply_text or "").lower()
            
            # Address collection buttons (including collect_address template buttons and flow buttons)
            if btn_id in ["ADD_DELIVERY_ADDRESS", "USE_CURRENT_LOCATION", "ENTER_NEW_ADDRESS", 
                         "USE_SAVED_ADDRESS", "CONFIRM_ADDRESS", "CHANGE_ADDRESS", "RETRY_ADDRESS",
                         "add_address", "use_location", "enter_manually", "saved_address",
                         "fill_form_step1", "share_location", "provide_address", "address_flow"]:
                try:
                    # Handle WhatsApp Flow buttons
                    if btn_id in ["provide_address", "address_flow"]:
                        # Flow button clicked - send the WhatsApp Flow
                        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                        await send_address_flow_button(wa_id, db, customer.name or "Customer")
                    
                    # Handle collect_address template buttons - any button from collect_address template opens the form
                    elif btn_id in ["add_address", "use_location", "enter_manually", "saved_address", "fill_form_step1", "share_location"]:
                        if btn_id == "add_address" or btn_id == "enter_manually" or btn_id == "fill_form_step1":
                            # Show structured address form using WhatsApp interactive message
                            await send_address_form(wa_id, db)
                        elif btn_id == "use_location" or btn_id == "share_location":
                            await send_message_to_waid(wa_id, "📍 Please share your current location by tapping the location icon below.", db)
                        elif btn_id == "saved_address":
                            await send_message_to_waid(wa_id, "💾 You can use a previously saved address. Please enter your address manually for now.", db)
                            await send_address_form(wa_id, db)
                    else:
                        # Handle other address collection buttons using the service
                        from services.address_collection_service import AddressCollectionService
                        address_service = AddressCollectionService(db)
                        result = await address_service.handle_address_button_click(wa_id, btn_id)
                        
                        if not result["success"]:
                            await send_message_to_waid(wa_id, f"❌ {result.get('error', 'Something went wrong')}", db)
                except Exception as e:
                    await send_message_to_waid(wa_id, f"❌ Error processing address request: {str(e)}", db)
            
            # Generic handler for any button click when user is awaiting address
            elif awaiting_address_users.get(wa_id, False):
                # If user is awaiting address and clicks any button, show the structured form
                await send_address_form(wa_id, db)
            
            # Buy Products button
            elif ("buy" in choice_text) or ("product" in choice_text) or (btn_id and str(btn_id).lower() in {"buy_products", "buy", "products"}):
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
            
            # Handle WhatsApp Flow submission
            if i_type == "flow":
                flow_response = interactive.get("flow_response", {})
                flow_token = flow_response.get("flow_token", "")
                flow_id = flow_response.get("flow_id", "")
                flow_cta = flow_response.get("flow_cta", "")
                flow_action_payload = flow_response.get("flow_action_payload", {})
                
                print(f"Flow response received: flow_id={flow_id}, flow_cta={flow_cta}")
                
                # Handle address collection flow
                if flow_id == "address_collection_flow" or "address" in flow_id.lower():
                    try:
                        # Extract address data from flow response
                        address_data = {}
                        
                        # Parse flow action payload for address fields
                        if flow_action_payload:
                            # Common field mappings for address flows
                            field_mappings = {
                                "full_name": ["full_name", "name", "customer_name"],
                                "phone_number": ["phone_number", "phone", "mobile"],
                                "house_street": ["house_street", "address_line_1", "street"],
                                "locality": ["locality", "area", "neighborhood"],
                                "city": ["city", "town"],
                                "state": ["state", "province"],
                                "pincode": ["pincode", "postal_code", "zip_code"],
                                "landmark": ["landmark", "landmark_nearby"]
                            }
                            
                            for field_name, possible_keys in field_mappings.items():
                                for key in possible_keys:
                                    if key in flow_action_payload:
                                        address_data[field_name] = flow_action_payload[key]
                                        break
                        
                        # Validate and save address
                        if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                            from schemas.address_schema import CustomerAddressCreate
                            from services.address_service import create_customer_address
                            
                            address_create = CustomerAddressCreate(
                                customer_id=customer.id,
                                full_name=address_data.get("full_name", ""),
                                house_street=address_data.get("house_street", ""),
                                locality=address_data.get("locality", ""),
                                city=address_data.get("city", ""),
                                state=address_data.get("state", ""),
                                pincode=address_data.get("pincode", ""),
                                landmark=address_data.get("landmark", ""),
                                phone=address_data.get("phone_number", customer.wa_id),
                                address_type="home",
                                is_default=True
                            )
                            
                            saved_address = create_customer_address(db, address_create)
                            
                            # Send confirmation
                            await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                            await send_message_to_waid(wa_id, f"📍 {saved_address.full_name}, {saved_address.house_street}, {saved_address.locality}, {saved_address.city} - {saved_address.pincode}", db)
                            
                            # Clear awaiting address flag
                            awaiting_address_users[wa_id] = False
                            
                            # Continue with payment flow
                            try:
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
                                    # Send payment link (using existing payment logic)
                                    from utils.razorpay_utils import create_razorpay_payment_link
                                    try:
                                        payment_resp = create_razorpay_payment_link(
                                            amount=float(total_amount),
                                            currency="INR",
                                            description=f"WA Order {str(latest_order.id) if latest_order else ''}"
                                        )
                                        pay_link = payment_resp.get("short_url") if isinstance(payment_resp, dict) else None
                                        if pay_link:
                                            await send_message_to_waid(wa_id, f"💳 Please complete your payment using this link: {pay_link}", db)
                                    except Exception as pay_err:
                                        print("Payment flow error:", pay_err)
                            except Exception as e:
                                print("Error in payment flow after address collection:", e)
                            
                            return {"status": "address_saved", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).", db)
                            return {"status": "flow_incomplete", "message_id": message_id}
                            
                    except Exception as e:
                        print(f"Error processing flow response: {e}")
                        await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                        return {"status": "flow_error", "message_id": message_id}
                
                return {"status": "flow_processed", "message_id": message_id}
            
            # Handle form submission
            elif i_type == "form":
                form_response = interactive.get("form_response", {})
                form_name = form_response.get("name", "")
                form_data = form_response.get("data", [])
                
                if form_name == "address_form":
                    # Process address form submission
                    try:
                        address_data = {}
                        for item in form_data:
                            field_id = item.get("id", "")
                            field_value = item.get("value", "")
                            address_data[field_id] = field_value
                        
                        # Validate and save address
                        if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                            # Create address using the new address service
                            from schemas.address_schema import CustomerAddressCreate
                            from services.address_service import create_customer_address
                            
                            address_create = CustomerAddressCreate(
                                customer_id=customer.id,
                                full_name=address_data.get("full_name", ""),
                                house_street=address_data.get("house_street", ""),
                                locality=address_data.get("locality", ""),
                                city=address_data.get("city", ""),
                                state=address_data.get("state", ""),
                                pincode=address_data.get("pincode", ""),
                                landmark=address_data.get("landmark", ""),
                                phone=address_data.get("phone_number", customer.wa_id),
                                address_type="home",
                                is_default=True
                            )
                            
                            saved_address = create_customer_address(db, address_create)
                            
                            # Send confirmation
                            await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                            await send_message_to_waid(wa_id, f"📍 {saved_address.full_name}, {saved_address.house_street}, {saved_address.locality}, {saved_address.city} - {saved_address.pincode}", db)
                            
                            # Clear awaiting address flag
                            awaiting_address_users[wa_id] = False
                            
                            # Continue with payment flow
                            try:
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
                                    # Send payment link (using existing payment logic)
                                    await send_message_to_waid(wa_id, f"💳 Please complete your payment of ₹{int(total_amount)} using the payment link that will be sent shortly.", db)
                            except Exception as pay_err:
                                print("Payment flow error:", pay_err)
                            
                            return {"status": "address_saved", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).", db)
                            return {"status": "form_incomplete", "message_id": message_id}
                            
                    except Exception as e:
                        print(f"Error processing address form: {e}")
                        await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                        return {"status": "form_error", "message_id": message_id}
            
            # Handle other interactive types (buttons, lists)
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