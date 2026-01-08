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
import tempfile
import subprocess
from pathlib import Path
from controllers.web_socket import manager
from auth import get_current_user
from models.models import User
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

PHONE_ID_MAP = {
    "917617613030": "859830643878412",
    "918297882978": "848542381673826",
    "917729992376": "367633743092037",
}

SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/aac",
    "audio/mp4",
    "audio/mpeg",
    "audio/mp3",
    "audio/amr",
    "audio/ogg",
    "audio/opus",
}


def _convert_audio_to_supported_format(file_bytes: bytes, filename: str, mime_type: str):
    """
    Converts unsupported audio (e.g. video/webm) to MP3 using ffmpeg so that Meta accepts it.
    """
    if mime_type in SUPPORTED_AUDIO_MIME_TYPES:
        return file_bytes, filename, mime_type

    src_suffix = Path(filename).suffix or (mimetypes.guess_extension(mime_type or "") or ".webm")
    src_path = None
    dst_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=src_suffix) as temp_src:
            temp_src.write(file_bytes)
            temp_src.flush()
            src_path = temp_src.name

        dst_path = f"{src_path}.mp3"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            dst_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Audio conversion failed: {result.stderr.decode('utf-8', 'ignore')}",
            )

        with open(dst_path, "rb") as converted_file:
            converted_bytes = converted_file.read()

        safe_name = Path(filename).stem or "audio"
        new_filename = f"{safe_name}.mp3"
        return converted_bytes, new_filename, "audio/mpeg"
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Audio conversion requires ffmpeg to be installed on the server.",
        )
    finally:
        try:
            if os.path.exists(src_path):
                os.remove(src_path)
        except Exception:
            pass
        try:
            if dst_path and os.path.exists(dst_path):
                os.remove(dst_path)
        except Exception:
            pass

def get_urls_by_peer(peer: str, db: Session = None):
    """
    Get WhatsApp API URLs and phone_id for a peer number.
    First checks hardcoded PHONE_ID_MAP, then looks up from database.
    """
    # First check hardcoded map (for backward compatibility)
    phone_id = PHONE_ID_MAP.get(peer)
    
    # If not found in hardcoded map, try database lookup
    if not phone_id and db:
        try:
            from controllers.webhook_controller import get_whatsapp_config_by_peer
            config = get_whatsapp_config_by_peer(db, peer)
            phone_id = config.get("phone_number_id")
            # Return config with API URLs (works for both Meta and alots.io)
            return {
                "messages": config["api_url"],
                "media": config["media_url"],
                "phone_id": phone_id,
                "token": config.get("token")  # Token may be available for alots.io numbers
            }
        except HTTPException:
            # Re-raise HTTPException (e.g., "Invalid peer number")
            raise
        except Exception as e:
            print(f"[whatsapp_controller] Database lookup failed for peer {peer}: {e}")
            import traceback
            traceback.print_exc()
            # Fall through to error if database lookup fails
    
    if not phone_id:
        raise HTTPException(status_code=400, detail=f"Invalid peer number: {peer}. Please ensure the WhatsApp number is registered in the database.")

    return {
        "messages": f"https://graph.facebook.com/v22.0/{phone_id}/messages",
        "media": f"https://graph.facebook.com/v22.0/{phone_id}/media",
        "phone_id": phone_id
    }
    
def _coerce_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    stripped = value.strip()
    if stripped == "":
        return None
    try:
        return float(stripped)
    except (ValueError, TypeError):
        return None
    
@router.post("/token", status_code=201)
def add_token(token_data: WhatsAppTokenCreate, db: Session = Depends(get_db)):
    try:
        create_whatsapp_token(db, token_data)
        return {"status": "success", "message": "Token saved securely"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/send-message")
async def send_whatsapp_message(
    peer: str = Form(...),
    wa_id: str = Form(...),
    type: Literal["text", "image", "document", "video", "audio", "interactive", "location", "template", "flow"] = Form(...),
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
    # Optional template button support (e.g. URL button with dynamic parameter)
    template_button_params: Optional[str] = Form(None),  # CSV or single value, e.g. "3WBCRqn"
    template_button_index: Optional[str] = Form("0"),  # WhatsApp buttons are 0-indexed
    template_button_sub_type: Optional[str] = Form("url"),
    # Flow-specific (for type == "flow")
    flow_id: Optional[str] = Form(None),
    flow_cta: Optional[str] = Form("Provide Address"),
    flow_token: Optional[str] = Form(None),
    flow_payload_json: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # Validate body for text messages
        if type == "text":
            if body is None or (isinstance(body, str) and not body.strip()):
                raise HTTPException(status_code=400, detail="Text body is required and cannot be empty for text messages")
        
        # Get URLs and config - try database lookup first, fallback to hardcoded map
        urls = get_urls_by_peer(peer, db)
        WHATSAPP_API_URL = urls["messages"]
        MEDIA_URL = urls["media"]
        
        # Get token - prefer from database config (for alots.io numbers), fallback to latest token
        token = urls.get("token")  # For alots.io numbers, token comes from config
        if not token:
            token_obj = whatsapp_service.get_latest_token(db)
            if not token_obj:
                raise HTTPException(status_code=400, detail="Token not available")
            token = token_obj.token
        
        headers = {"Authorization": f"Bearer {token}"}
        from_wa_id = peer  # sender changes based on peer
        media_id = None
        caption = None
        filename = None
        mime_type = None
        uploaded_filename = None
        # Always define; used later when saving message even for non-template types
        effective_media_id = None

        # ---------------- Upload media if file is provided ----------------
        if file:
            uploaded_filename = file.filename or "upload"
            mime_type = file.content_type or mimetypes.guess_type(uploaded_filename)[0]
            if not mime_type:
                raise HTTPException(status_code=400, detail="Invalid file type")
            file_bytes = await file.read()

            if type == "audio":
                file_bytes, uploaded_filename, mime_type = _convert_audio_to_supported_format(
                    file_bytes, uploaded_filename, mime_type
                )

            files = {
                "file": (uploaded_filename, file_bytes, mime_type),
                "messaging_product": (None, "whatsapp")
            }
            upload_res = requests.post(MEDIA_URL, headers=headers, files=files)
            if upload_res.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Media upload failed: {upload_res.text}")
            media_id = upload_res.json().get("id")
            # Set effective_media_id for images, videos, and documents
            effective_media_id = media_id

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "recipient_type": "individual",
            "type": type
        }

        coerced_latitude = _coerce_float(latitude)
        coerced_longitude = _coerce_float(longitude)

        # ---------------- Text Message ----------------
        if type == "text":
            # Validate body early
            if body is None:
                raise HTTPException(status_code=400, detail="Text body is required for text messages")
            if not isinstance(body, str):
                body = str(body) if body else ""
            body = body.strip()
            if not body:
                raise HTTPException(status_code=400, detail="Text body cannot be empty")
            
            # Set text payload - this is required by WhatsApp API
            payload["text"] = {
                "body": body,
                "preview_url": False
            }
            print(f"[whatsapp_controller] Text message - body: '{body}', payload: {json.dumps(payload, indent=2)}")

        # ---------------- Image Message ----------------
        elif type == "image":
            if not media_id:
                raise HTTPException(status_code=400, detail="Image upload failed")
            payload["image"] = {"id": media_id, "caption": body or ""}

        # ---------------- Document Message ----------------
        elif type == "document":
            if not media_id:
                raise HTTPException(status_code=400, detail="Document upload failed")
            doc_name = uploaded_filename or (file.filename if file else None)
            payload["document"] = {"id": media_id, "caption": body or "", "filename": doc_name}

        # ---------------- Video Message ----------------
        elif type == "video":
            if not media_id:
                raise HTTPException(status_code=400, detail="Video upload failed")
            payload["video"] = {"id": media_id}
            if body:
                payload["video"]["caption"] = body

        # ---------------- Audio Message ----------------
        elif type == "audio":
            if not media_id:
                raise HTTPException(status_code=400, detail="Audio upload failed")
            payload["audio"] = {"id": media_id}
            effective_media_id = media_id

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
            if coerced_latitude is None or coerced_longitude is None:
                raise HTTPException(status_code=400, detail="Latitude and Longitude must be numeric for location messages")
            payload["location"] = {"latitude": str(coerced_latitude), "longitude": str(coerced_longitude)}
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

            # ---------------- Parse template_params (header/body) ----------------
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

                # Add text header params (only if no media header)
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

            # ---------------- Button parameters (e.g. URL button) ----------------
            if template_button_params:
                try:
                    reader = csv.reader(io.StringIO(template_button_params))
                    row = next(reader, [])
                    btn_param_list = [p.strip() for p in row]
                except Exception:
                    btn_param_list = [p.strip() for p in template_button_params.split(",") if p]

                if btn_param_list:
                    # Convert button_index to integer (WhatsApp API requires integer, not string)
                    try:
                        button_index_int = int(str(template_button_index or "0").strip())
                    except (ValueError, AttributeError):
                        button_index_int = 0
                    button_component = {
                        "type": "button",
                        "sub_type": str(template_button_sub_type or "url"),
                        "index": button_index_int,  # WhatsApp API requires integer, not string
                        "parameters": [
                            {"type": "text", "text": v} for v in btn_param_list
                        ]
                    }
                    components.append(button_component)

            # ---------------- Image Header ----------------
            effective_media_id = template_media_id or media_id
            if effective_media_id:
                # Determine if it's a URL or a media ID
                # URLs start with http/https, resumable handles start with "4:" and are very long
                # WhatsApp media IDs are typically numeric strings
                is_url = effective_media_id.startswith("http://") or effective_media_id.startswith("https://")
                is_resumable_handle = effective_media_id.startswith("4:") and len(effective_media_id) > 50

                if is_url:
                    # Use link for URLs
                    image_param = {"link": effective_media_id}
                elif is_resumable_handle:
                    # Resumable upload handles can't be used for sending - need URL or media ID
                    # Try to use it anyway, but this will likely fail
                    image_param = {"id": effective_media_id}
                else:
                    # Regular WhatsApp media ID
                    image_param = {"id": effective_media_id}

                components.insert(0, {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": image_param
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
        print(f"[whatsapp_controller] Sending {type} message to {wa_id} via {peer}")
        print(f"[whatsapp_controller] API URL: {WHATSAPP_API_URL}")
        print(f"[whatsapp_controller] Payload: {json.dumps(payload, indent=2)}")
        
        res = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers={**headers, "Content-Type": "application/json"}
        )

        if res.status_code != 200:
            print(f"[whatsapp_controller] Error response: {res.status_code} - {res.text}")
            raise HTTPException(status_code=500, detail=f"Failed to send message: {res.text}")

        message_id = res.json()["messages"][0]["id"]

        # ---------------- Save in DB ----------------
        customer_data = CustomerCreate(wa_id=wa_id, name="")
        customer = customer_service.get_or_create_customer(db, customer_data)

        agent_identifier = str(current_user.id)
        agent_display_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.username or current_user.email

        message_data = MessageCreate(
            message_id=message_id,
            from_wa_id=from_wa_id,
            to_wa_id=wa_id,
            type=type,
            body=body or "",
            timestamp=datetime.now(),
            customer_id=customer.id,
            media_id=effective_media_id,
            caption=body if type in ["image", "document", "video"] else None,
            filename=uploaded_filename if file else None,
            latitude=coerced_latitude,
            longitude=coerced_longitude,
            mime_type=mime_type,
            agent_id=agent_identifier,
            sender_type="agent",
            agent_role=current_user.role,
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
            "mime_type": message.mime_type,
            "agent_id": agent_identifier,
            "agent_name": agent_display_name,
            "sender_type": "agent",
            "agent_role": current_user.role,
        })

        return {
            "status": "success", 
            "message_id": message.message_id,
            "media_id": message.media_id,
            "mime_type": message.mime_type,
            "filename": message.filename
        }

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
