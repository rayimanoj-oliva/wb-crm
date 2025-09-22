from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse
from typing import Optional, Literal
from datetime import datetime
import requests
import json
import csv
import io
import mimetypes
import httpx
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
import os
from controllers.web_socket import manager
from schemas.campaign_schema import CampaignOut
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from schemas.template_schema import SendTemplateRequest
from schemas.whatsapp_token_schema import WhatsAppTokenCreate
from database.db import get_db
from services import customer_service, message_service, whatsapp_service
from services.whatsapp_service import create_whatsapp_token, get_latest_token

router = APIRouter(tags=["WhatsApp Token"])

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"
MEDIA_URL = "https://graph.facebook.com/v22.0/367633743092037/media"
# MEDIA_URL = "https://graph.facebook.com/v22.0/286831244524604/media"


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
    type: Literal["text", "image", "document", "interactive", "location", "template", "flow"] = Form(...),
    body: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    location_name: Optional[str] = Form(None),
    location_address: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    language: Optional[str] = Form("en_US"),
    template_params: Optional[str] = Form(None),
    template_auto_fix: Optional[bool] = Form(False),
    template_header_params: Optional[int] = Form(None),
    template_body_expected: Optional[int] = Form(None),
    template_enforce_count: Optional[bool] = Form(False),
    template_media_id: Optional[str] = Form(None),
    # Flow-specific (for type == "flow")
    flow_id: Optional[str] = Form(None),
    flow_cta: Optional[str] = Form("Provide Address"),
    flow_token: Optional[str] = Form(None),
    flow_payload_json: Optional[str] = Form(None),
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

        # ---------------- Upload media if file is provided ----------------
        if file:
            mime_type = mimetypes.guess_type(file.filename)[0]
            if not mime_type:
                raise HTTPException(status_code=400, detail="Invalid file type")
            files = {
                "file": (file.filename, await file.read(), mime_type),
                "messaging_product": (None, "whatsapp")
            }
            upload_res = requests.post(MEDIA_URL, headers=headers, files=files)
            if upload_res.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Media upload failed: {upload_res.text}")
            media_id = upload_res.json().get("id")

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "recipient_type": "individual",
            "type": type
        }

        # ---------------- Text Message ----------------
        if type == "text":
            if not body:
                raise HTTPException(status_code=400, detail="Text body required")
            payload["text"] = {"body": body, "preview_url": False}

        # ---------------- Image Message ----------------
        elif type == "image":
            if not media_id:
                raise HTTPException(status_code=400, detail="Image upload failed")
            payload["image"] = {"id": media_id, "caption": body or ""}

        # ---------------- Document Message ----------------
        elif type == "document":
            if not media_id:
                raise HTTPException(status_code=400, detail="Document upload failed")
            payload["document"] = {"id": media_id, "caption": body or "", "filename": file.filename}

        # ---------------- Interactive Message ----------------
        elif type == "interactive":
            payload["interactive"] = {
                "type": "product_list",
                "header": {"type": "text", "text": "Oliva Skin Solutions"},
                "body": {"text": "Here are some products just for you"},
                "footer": {"text": "Tap to view each product"},
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

        # ---------------- Location Message ----------------
        elif type == "location":
            if not latitude or not longitude:
                raise HTTPException(status_code=400, detail="Latitude and Longitude are required")
            payload["location"] = {"latitude": latitude, "longitude": longitude}
            if location_name:
                payload["location"]["name"] = location_name
            if location_address:
                payload["location"]["address"] = location_address
            body = f"{location_name or ''} - {location_address or ''}"

        # ---------------- Template Message ----------------
        elif type == "template":
            if not template_name:
                raise HTTPException(status_code=400, detail="Template name is required")

            components = []

            # ---------------- Parse template_params ----------------
            if template_params:
                try:
                    reader = csv.reader(io.StringIO(template_params))
                    row = next(reader, [])
                    param_list = [p.strip() for p in row]
                except Exception:
                    param_list = [p.strip() for p in template_params.split(",") if p]

                header_count = int(template_header_params) if template_header_params else 0
                header_vals = param_list[:header_count] if header_count > 0 else []
                body_vals = param_list[header_count:] if header_count >= 0 else param_list

                if template_enforce_count and template_body_expected:
                    expected = int(template_body_expected)
                    if len(body_vals) < expected:
                        body_vals += [""] * (expected - len(body_vals))
                    elif len(body_vals) > expected:
                        body_vals = body_vals[:expected]

                # Add text header params
                if header_vals and not (template_media_id or media_id):
                    components.append({
                        "type": "header",
                        "parameters": [{"type": "text", "text": v} for v in header_vals]
                    })
                # Add body params
                if body_vals:
                    components.append({
                        "type": "body",
                        "parameters": [{"type": "text", "text": v} for v in body_vals]
                    })

            # ---------------- Image Header ----------------
            effective_media_id = template_media_id or media_id
            if effective_media_id:
                # Correct structure: image inside parameters, no "format"
                components.insert(0, {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {"id": effective_media_id}
                        }
                    ]
                })

            payload["template"] = {
                "name": template_name,
                "language": {"code": language},
                "components": components
            }

            body = f"TEMPLATE: {template_name} - Params: {template_params}"

        # ---------------- Flow Interactive (opens native WhatsApp Flow) ----------------
        elif type == "flow":
            if not flow_id:
                raise HTTPException(status_code=400, detail="flow_id is required for type=flow")

            try:
                action_payload = json.loads(flow_payload_json) if flow_payload_json else {}
            except Exception:
                action_payload = {}

            payload["type"] = "interactive"
            payload["interactive"] = {
                "type": "flow",
                "header": {"type": "text", "text": "\ud83d\udccd Address Collection"},
                "body": {"text": body or "Please provide your delivery address using the form below."},
                "footer": {"text": "All fields are required for delivery"},
                "action": {
                    "name": "flow",
                    "parameters": {
                        "flow_message_version": "3",
                        "flow_id": flow_id,
                        "flow_cta": flow_cta or "Open",
                        **({"flow_token": flow_token} if flow_token else {}),
                        **({"flow_action_payload": action_payload} if action_payload else {})
                    }
                }
            }
            body = f"FLOW: {flow_id}"

        # ---------------- Send Request ----------------
        res = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers={**headers, "Content-Type": "application/json"}
        )

        if res.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to send message: {res.text}")

        message_id = res.json()["messages"][0]["id"]

        # ---------------- Save in DB ----------------
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
            media_id=effective_media_id,
            caption=body if type in ["image", "document"] else None,
            filename=file.filename if file else None,
            latitude=latitude,
            longitude=longitude,
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
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    headers = {"Authorization": f"Bearer {token}"}

    metadata_url = f"https://graph.facebook.com/v23.0/{media_id}"
    meta_res = requests.get(metadata_url, headers=headers)

    if meta_res.status_code != 200:
        raise HTTPException(status_code=meta_res.status_code, detail="Failed to fetch media metadata")

    media_url = meta_res.json().get("url")
    if not media_url:
        raise HTTPException(status_code=400, detail="Media URL not found")

    media_res = requests.get(media_url, headers=headers, stream=True)
    if media_res.status_code != 200:
        raise HTTPException(status_code=media_res.status_code, detail="Failed to download media")

    content_type = media_res.headers.get("Content-Type", "application/octet-stream")
    return StreamingResponse(media_res.raw, media_type=content_type)



# ⚠️ Use your permanent WhatsApp Cloud API token here or from env
# WHATSAPP_TOKEN = "YOUR_WA_CLOUD_API_ACCESS_TOKEN"

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
_EXTENSION_FALLBACK = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "audio/mpeg": ".mp3",
    "video/mp4": ".mp4",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

def _safe_filename(name: str) -> str:
    # simple sanitiser: allow alnum, dot, underscore, dash
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9.\-_]", "_", name)

@router.get("/download/{media_id}")
async def download_media(media_id: str, db: Session = Depends(get_db)):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    # Step 1: request media metadata (returns a temporary 'url')
    async with httpx.AsyncClient() as client:
        meta_resp = await client.get(f"https://graph.facebook.com/v21.0/{media_id}",
                                     headers={"Authorization": f"Bearer {token}"})
    if meta_resp.status_code != 200:
        raise HTTPException(status_code=meta_resp.status_code, detail=f"Failed to fetch media metadata: {meta_resp.text}")

    meta = meta_resp.json()
    media_url = meta.get("url")
    provided_name = meta.get("filename") or meta.get("name")  # metadata may include filename/name
    meta_mime = meta.get("mime_type")

    if not media_url:
        raise HTTPException(status_code=404, detail="Media URL not found in metadata")

    # Step 2: stream the file from the media URL (use same Bearer token)
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", media_url, headers={"Authorization": f"Bearer {token}"}) as file_resp:
            if file_resp.status_code != 200:
                raise HTTPException(status_code=file_resp.status_code, detail=f"Failed to download media: {await file_resp.aread()}")

            # determine content-type and extension
            content_type = (file_resp.headers.get("Content-Type") or meta_mime or "application/octet-stream").split(";")[0].strip()
            ext = mimetypes.guess_extension(content_type)
            if not ext:
                # try metadata mime_type
                if meta_mime:
                    ext = mimetypes.guess_extension(meta_mime.split(";")[0].strip())
            if not ext:
                # fallback to manual map
                ext = _EXTENSION_FALLBACK.get(content_type, "")

            # choose filename
            if provided_name:
                base, cur_ext = os.path.splitext(provided_name)
                if not cur_ext and ext:
                    provided_name = base + ext
                filename = _safe_filename(provided_name)
            else:
                filename = f"{media_id}{ext}"

            file_path = os.path.join(DOWNLOAD_DIR, filename)

            # stream-to-disk
            with open(file_path, "wb") as f:
                async for chunk in file_resp.aiter_bytes():
                    if chunk:
                        f.write(chunk)

    # Step 3: return the file (FileResponse sets Content-Disposition with filename)
    return FileResponse(path=file_path, filename=filename, media_type=content_type)

