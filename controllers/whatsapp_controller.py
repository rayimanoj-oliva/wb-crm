from fastapi import APIRouter
from sqlalchemy import nullsfirst
from starlette.responses import StreamingResponse

from controllers.web_socket import manager
from schemas.campaign_schema import CampaignOut
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from schemas.template_schema import SendTemplateRequest
from schemas.whatsapp_token_schema import WhatsAppTokenCreate
from database.db import get_db
from services import customer_service, message_service, whatsapp_service
from services.whatsapp_service import create_whatsapp_token, get_latest_token

from fastapi import UploadFile, File, Form, Depends, HTTPException
from typing import Optional, Literal
from sqlalchemy.orm import Session
import requests
import mimetypes
from datetime import datetime

router = APIRouter(tags=["WhatsApp Token"])

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"
MEDIA_URL = "https://graph.facebook.com/v22.0/367633743092037/media"


@router.post("/token", status_code=201)
def add_token(token_data: WhatsAppTokenCreate, db: Session = Depends(get_db)):
    try:
        create_whatsapp_token(db, token_data)
        return {"status": "success", "message": "Token saved securely"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send-message")
async def send_whatsapp_message(
    wa_id: str = Form(...),
    type: Literal["text", "image", "document", "interactive", "location"] = Form(...),  # <-- ✅ ADDED "location"
    body: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    latitude: Optional[str] = Form(None),              # <-- ✅ ADDED
    longitude: Optional[str] = Form(None),             # <-- ✅ ADDED
    location_name: Optional[str] = Form(None),         # <-- ✅ ADDED
    location_address: Optional[str] = Form(None),      # <-- ✅ ADDED
    db: Session = Depends(get_db)
):
    try:
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise HTTPException(status_code=400, detail="Token not available")

        token = token_obj.token
        headers = {"Authorization": f"Bearer {token}"}
        from_wa_id = "917729992376"

        media_id = None
        caption = None
        filename = None
        mime_type = None

        if file:
            mime_type = mimetypes.guess_type(file.filename)[0]
            if not mime_type:
                raise HTTPException(status_code=400, detail="Invalid file type")

            files = {
                "file": (file.filename, await file.read(), mime_type),
                "messaging_product": (None, "whatsapp")
            }

            upload_res = requests.post(f"{MEDIA_URL}", headers=headers, files=files)
            if upload_res.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Media upload failed: {upload_res.text}")
            media_id = upload_res.json().get("id")

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "recipient_type": "individual",
            "type": type
        }

        if type == "text":
            if not body:
                raise HTTPException(status_code=400, detail="Text body required")
            payload["text"] = {"body": body, "preview_url": False}

        elif type == "image":
            if not media_id:
                raise HTTPException(status_code=400, detail="Image upload failed")
            caption = body or ""
            payload["image"] = {"id": media_id, "caption": caption}

        elif type == "document":
            if not media_id:
                raise HTTPException(status_code=400, detail="Document upload failed")
            caption = body or ""
            filename = file.filename
            payload["document"] = {
                "id": media_id,
                "caption": caption,
                "filename": filename
            }

        elif type == "interactive":
            payload["interactive"] = {
                "type": "product_list",
                "header": {
                    "type": "text",
                    "text": "Oliva Skin Solutions"
                },
                "body": {
                    "text": "Here are some products just for you"
                },
                "footer": {
                    "text": "Tap to view each product"
                },
                "action": {
                    "catalog_id": "1093353131080785",
                    "sections": [
                        {
                            "title": "Skin Care Combos",
                            "product_items": [
                                {"product_retailer_id": "39302163202202"},
                                {"product_retailer_id": "39531958435994"},
                                {"product_retailer_id": "35404294455450"},
                                {"product_retailer_id": "35411030081690"},
                                {"product_retailer_id": "40286295392410"}
                            ]
                        }
                    ]
                }
            }
            body = "5 Products"

        elif type == "location":  # <-- ✅ LOCATION SUPPORT
            if not latitude or not longitude:
                raise HTTPException(status_code=400, detail="Latitude and Longitude are required")
            payload["location"] = {
                "latitude": latitude,
                "longitude": longitude
            }
            if location_name:
                payload["location"]["name"] = location_name
            if location_address:
                payload["location"]["address"] = location_address
            body = f"{location_name or ''} - {location_address or ''}"

        res = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers={**headers, "Content-Type": "application/json"}
        )

        if res.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to send message: {res.text}")

        message_id = res.json()["messages"][0]["id"]

        customer_data = CustomerCreate(wa_id=wa_id, name="")
        customer = customer_service.get_or_create_customer(db, customer_data)

        message_data = MessageCreate(
            message_id=message_id,
            from_wa_id=from_wa_id,
            to_wa_id=wa_id,
            type=type,
            body=body or "",
            timestamp=datetime.now(),
            customer_id=customer.id,
            media_id=media_id,
            caption=caption,
            filename=filename,
            mime_type=mime_type
        )
        message = message_service.create_message(db, message_data)

        await manager.broadcast({
            "from": message.from_wa_id,
            "to": message.to_wa_id,
            "type": message.type,
            "message": message.body,
            "timestamp": message.timestamp.isoformat(),
            "media_id": message.media_id,
            "caption": message.caption,
            "filename": message.filename,
            "mime_type": message.mime_type
        })

        return {"status": "success", "message_id": message.message_id}

    except Exception as e:
        return {"status": "failed", "error": str(e)}
    

@router.get("/get-image")
def get_image(media_id: str, db: Session = Depends(get_db)):
    # 1. Get the latest access token
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Fetch media URL using media_id
    metadata_url = f"https://graph.facebook.com/v23.0/{media_id}"
    meta_res = requests.get(metadata_url, headers=headers)

    if meta_res.status_code != 200:
        raise HTTPException(status_code=meta_res.status_code, detail="Failed to fetch media metadata")

    media_url = meta_res.json().get("url")
    if not media_url:
        raise HTTPException(status_code=400, detail="Media URL not found")

    # 3. Fetch the actual media file from media URL
    media_res = requests.get(media_url, headers=headers, stream=True)
    if media_res.status_code != 200:
        raise HTTPException(status_code=media_res.status_code, detail="Failed to download media")

    content_type = media_res.headers.get("Content-Type", "application/octet-stream")

    # 4. Return the media as a streamed response
    return StreamingResponse(media_res.raw, media_type=content_type)