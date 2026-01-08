from datetime import datetime
import os
import json

from fastapi import Request, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Form, UploadFile, File
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import Any, Optional, Literal, List
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse
import asyncio
import httpx
import requests
from pydantic import BaseModel

from database.db import get_db
from controllers.utils.debug_window import debug_webhook_payload
from services import customer_service, message_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from models.models import Message, User
from utils.ws_manager import manager
from auth import get_current_user

# =============================================================================
# CONFIG
# =============================================================================

# VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

# Alots.io Configuration (fallback for numbers not in database)
ALOTS_CONFIG = {
    "917416159696": {
        "phone_number_id": "916824348188229",
        "token": "c0b140ef-a10a-4d2c-a6b0-e5f65668551c",
        "api_base_url": "https://alots.io/v22.0",
        "display_name": "Oasis Fertility"
    }
}

def get_whatsapp_config_by_peer(db: Session, peer: str):
    """
    Get WhatsApp API config for a peer number (display_number or phone_number_id)
    Looks up from whatsapp_numbers table, falls back to ALOTS_CONFIG
    """
    from services.whatsapp_number_service import get_whatsapp_number_by_phone_id
    from models.models import WhatsAppNumber
    import re

    # Normalize peer: remove all non-digits for comparison
    peer_digits = re.sub(r"\D", "", peer)

    print(f"[webhook2] Looking up peer: {peer} (normalized: {peer_digits})")

    # Check ALOTS_CONFIG first (for alots.io numbers)
    if peer in ALOTS_CONFIG:
        config = ALOTS_CONFIG[peer]
        print(f"[webhook2] Found in ALOTS_CONFIG: {config['display_name']}")
        return {
            "api_url": f"{config['api_base_url']}/{config['phone_number_id']}/messages",
            "media_url": f"{config['api_base_url']}/{config['phone_number_id']}/media",
            "token": config["token"],
            "phone_number_id": config["phone_number_id"],
            "display_name": config.get("display_name", peer)
        }
    
    # Try to find by phone_number_id first (exact match)
    whatsapp_number = get_whatsapp_number_by_phone_id(db, peer)
    if whatsapp_number:
        print(f"[webhook2] Found by phone_number_id: {whatsapp_number.phone_number_id}")
    
    # If not found, try to find by display_number
    if not whatsapp_number:
        # Try exact match on display_number
        whatsapp_number = db.query(WhatsAppNumber).filter(
            WhatsAppNumber.display_number == peer
        ).first()
        if whatsapp_number:
            print(f"[webhook2] Found by exact display_number match: {whatsapp_number.display_number}")
    
    # If still not found, try normalized digit match on display_number
    if not whatsapp_number and peer_digits:
        # Query ALL numbers first (for debugging and to avoid boolean filter issues)
        all_numbers = db.query(WhatsAppNumber).all()
        print(f"[webhook2] Found {len(all_numbers)} total numbers in database, filtering for active ones...")
        
        # Filter active numbers in Python (more reliable than SQL boolean comparison)
        active_numbers = [num for num in all_numbers if num.is_active is True]
        print(f"[webhook2] Trying normalized match on {len(active_numbers)} active numbers...")
        
        for num in active_numbers:
            if num.display_number:
                num_digits = re.sub(r"\D", "", num.display_number)
                print(f"[webhook2] Comparing: peer_digits={peer_digits} vs num_digits={num_digits} (from {num.display_number})")
                # Try full digit match
                if num_digits == peer_digits:
                    whatsapp_number = num
                    print(f"[webhook2] Found by normalized display_number match: {num.display_number} -> {num.phone_number_id}")
                    break
                # Try last 10 digits match (for numbers with country codes)
                if len(peer_digits) >= 10 and len(num_digits) >= 10:
                    peer_last10 = peer_digits[-10:]
                    num_last10 = num_digits[-10:]
                    if peer_last10 == num_last10:
                        whatsapp_number = num
                        print(f"[webhook2] Found by last 10 digits match: {num.display_number} (last10: {num_last10}) -> {num.phone_number_id}")
                        break
    
    # Debug: List all available numbers if still not found
    if not whatsapp_number:
        all_numbers = db.query(WhatsAppNumber).all()
        print(f"[webhook2] DEBUG - All WhatsApp numbers in database:")
        for num in all_numbers:
            print(f"  - phone_number_id: {num.phone_number_id}, display_number: {num.display_number}, is_active: {num.is_active}")
    
    if not whatsapp_number:
        all_numbers = db.query(WhatsAppNumber).all()
        active_numbers = [num for num in all_numbers if num.is_active is True]
        available_list = ", ".join([f"{num.display_number or num.phone_number_id}" for num in active_numbers[:5]])
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid or inactive peer number: {peer}. Please ensure the WhatsApp number is registered and active in the database. Available numbers: {available_list if available_list else 'None'}"
        )
    
    if not whatsapp_number.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Inactive peer number: {peer}. The WhatsApp number exists but is marked as inactive."
        )
    
    # Get access token (prefer from whatsapp_number, fallback to latest token)
    access_token = whatsapp_number.access_token
    if not access_token:
        from services.whatsapp_service import get_latest_token
        token_obj = get_latest_token(db)
        if token_obj:
            access_token = token_obj.token
            print(f"[webhook2] Using fallback token from whatsapp_service")
    
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail=f"No access token available for peer: {peer}. Please configure access_token for this WhatsApp number (phone_number_id: {whatsapp_number.phone_number_id})."
        )
    
    phone_number_id = whatsapp_number.phone_number_id
    print(f"[webhook2] Successfully resolved peer {peer} -> phone_number_id: {phone_number_id}")
    
    return {
        "api_url": f"https://graph.facebook.com/v22.0/{phone_number_id}/messages",
        "media_url": f"https://graph.facebook.com/v22.0/{phone_number_id}/media",
        "token": access_token,
        "phone_number_id": phone_number_id,
        "display_name": whatsapp_number.display_number or phone_number_id
    }

router = APIRouter(
    prefix="/webhook",
    tags=["Webhook"]
)

router2 = APIRouter(
    prefix="/webhook2",
    tags=["Webhook2"]
)

# =============================================================================
# COMMON UTILS
# =============================================================================

def log_webhook(payload: str, prefix: str):
    try:
        log_dir = "webhook_logs"
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        raw_path = os.path.join(log_dir, f"{prefix}_{ts}.json")

        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(payload)

        try:
            formatted = json.dumps(json.loads(payload), indent=2, ensure_ascii=False)
            with open(raw_path.replace(".json", "_formatted.json"), "w", encoding="utf-8") as f:
                f.write(formatted)
        except Exception:
            pass
    except Exception as e:
        print(f"[{prefix}] LOG ERROR:", e)

# =============================================================================
# WEBHOOK 1
# =============================================================================

@router.post("")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        raw = await request.body()
        raw_str = raw.decode("utf-8", errors="replace")
        body = json.loads(raw_str)

        log_webhook(raw_str, "webhook")
        debug_webhook_payload(body, raw_str)

        if "entry" not in body:
            return {"status": "ignored"}

        value = body["entry"][0]["changes"][0]["value"]

        if "statuses" in value and "messages" not in value:
            return {"status": "ok", "message": "Status ignored"}

        contact = value["contacts"][0]
        message = value["messages"][0]

        wa_id = contact["wa_id"]
        sender = contact["profile"]["name"]
        msg_type = message["type"]
        phone_number_id = value["metadata"]["phone_number_id"]

        print(
            f"[webhook] Message from {wa_id} ({sender}), "
            f"type={msg_type}, phone_id={phone_number_id}"
        )

        return {"status": "ok"}

    except Exception as e:
        print("[webhook] ERROR:", e)
        return {"status": "failed", "error": str(e)}


@router.get("")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[webhook] VERIFIED")
        return PlainTextResponse(content=challenge)

    raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/logs")
async def get_webhook_logs(limit: int = 20):
    """View recent webhook logs from browser"""
    try:
        log_dir = "webhook_logs"
        if not os.path.exists(log_dir):
            return {"logs": [], "message": "No logs folder yet"}

        files = [f for f in os.listdir(log_dir) if f.startswith("webhook_") and "_formatted" in f]
        files.sort(reverse=True)
        files = files[:limit]

        logs = []
        for filename in files:
            filepath = os.path.join(log_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = json.loads(f.read())
                    logs.append({
                        "file": filename,
                        "timestamp": filename.replace("webhook_", "").replace("_formatted.json", ""),
                        "data": content
                    })
            except Exception as e:
                logs.append({"file": filename, "error": str(e)})

        return {"total": len(logs), "logs": logs}
    except Exception as e:
        return {"error": str(e)}


@router.get("/logs/all")
async def get_all_webhook_logs(limit: int = 50):
    """View ALL webhook logs (webhook + webhook2)"""
    try:
        log_dir = "webhook_logs"
        if not os.path.exists(log_dir):
            return {"logs": [], "message": "No logs folder yet"}

        files = [f for f in os.listdir(log_dir) if "_formatted" in f]
        files.sort(reverse=True)
        files = files[:limit]

        logs = []
        for filename in files:
            filepath = os.path.join(log_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = json.loads(f.read())
                    logs.append({
                        "file": filename,
                        "data": content
                    })
            except Exception as e:
                logs.append({"file": filename, "error": str(e)})

        return {"total": len(logs), "logs": logs}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WEBHOOK 2
# =============================================================================

@router2.post("")
async def receive_webhook2(request: Request, db: Session = Depends(get_db)):
    """
    Webhook2 handler for second WhatsApp account (alots.io - phone_id: 916824348188229)
    - Receives incoming customer messages
    - Stores messages in database
    - Broadcasts to WebSocket for real-time UI updates
    """
    raw_str = ""
    try:
        raw = await request.body()
        raw_str = raw.decode("utf-8", errors="replace")

        # Log raw data FIRST - before any processing
        log_webhook(raw_str, "webhook2")

        body = json.loads(raw_str)
        debug_webhook_payload(body, raw_str)

        if "entry" not in body:
            return {"status": "ignored"}

        value = body["entry"][0]["changes"][0]["value"]

        # Skip status updates (delivery receipts, read receipts, etc.)
        if "statuses" in value and "messages" not in value:
            return {"status": "ok", "message": "Status ignored"}

        # Verify we have messages and contacts
        if "messages" not in value or "contacts" not in value:
            print(f"[webhook2] ERROR - Missing 'messages' or 'contacts' in webhook payload")
            return {"status": "error", "message": "Invalid webhook payload"}

        contact = value["contacts"][0]
        message = value["messages"][0]

        wa_id = contact["wa_id"]
        sender_name = contact["profile"]["name"]
        message_type = message["type"]
        message_id = message["id"]
        phone_number_id = value["metadata"]["phone_number_id"]
        from_wa_id = message["from"]
        to_wa_id = value["metadata"]["display_phone_number"]
        timestamp = datetime.fromtimestamp(int(message["timestamp"]))

        print(
            f"[webhook2] Message from {wa_id} ({sender_name}), "
            f"type={message_type}, phone_id={phone_number_id}"
        )

        # Extract message body based on type
        body_text = ""
        try:
            if message_type == "text":
                body_text = message.get("text", {}).get("body", "")
            elif message_type == "interactive":
                interactive = message.get("interactive", {})
                i_type = interactive.get("type")
                if i_type == "button_reply":
                    br = interactive.get("button_reply", {})
                    body_text = br.get("title", "") or br.get("id", "")
                elif i_type == "list_reply":
                    lr = interactive.get("list_reply", {})
                    body_text = lr.get("title", "") or lr.get("id", "")
                elif i_type == "nfm_reply":
                    nfm = interactive.get("nfm_reply", {})
                    response_json = nfm.get("response_json", "{}")
                    try:
                        response_data = json.loads(response_json)
                        form_fields = []
                        for key, val in response_data.items():
                            if val and str(val).strip():
                                form_fields.append(f"{key}: {val}")
                        body_text = " | ".join(form_fields) if form_fields else "Form submitted"
                    except:
                        body_text = "Form submitted"
            elif message_type == "button":
                btn = message.get("button", {})
                body_text = btn.get("text") or btn.get("payload") or ""
            elif message_type == "image":
                body_text = message.get("image", {}).get("caption", "[Image]")
            elif message_type == "document":
                body_text = message.get("document", {}).get("caption", "[Document]")
            elif message_type == "audio":
                body_text = "[Audio message]"
            elif message_type == "video":
                body_text = message.get("video", {}).get("caption", "[Video]")
            elif message_type == "location":
                loc = message.get("location", {})
                body_text = f"[Location: {loc.get('latitude')}, {loc.get('longitude')}]"
            elif message_type == "sticker":
                body_text = "[Sticker]"
            elif message_type == "contacts":
                body_text = "[Contact shared]"
        except Exception as e:
            print(f"[webhook2] WARN - Could not extract body_text: {e}")
            body_text = f"[{message_type}]"

        # Look up organization from phone_number_id
        organization_id = None
        if phone_number_id:
            try:
                from services.whatsapp_number_service import get_organization_by_phone_id
                organization = get_organization_by_phone_id(db, str(phone_number_id))
                if organization:
                    organization_id = organization.id
                    print(f"[webhook2] DEBUG - Found organization {organization.name} (id: {organization_id})")
            except Exception as e:
                print(f"[webhook2] WARNING - Could not look up organization: {e}")

        # Get or create customer
        customer = customer_service.get_or_create_customer(
            db,
            CustomerCreate(wa_id=wa_id, name=sender_name),
            organization_id=organization_id
        )

        # Check if message already exists (avoid duplicates)
        existing_msg = db.query(Message).filter(Message.message_id == message_id).first()
        if existing_msg:
            print(f"[webhook2] DEBUG - Message already exists: {message_id}")
            return {"status": "ok", "message": "Duplicate message ignored"}

        # Save message to database
        new_message = MessageCreate(
            message_id=message_id,
            from_wa_id=from_wa_id,
            to_wa_id=to_wa_id,
            type=message_type,
            body=body_text,
            timestamp=timestamp,
            customer_id=customer.id
        )
        message_service.create_message(db, new_message)
        db.commit()
        print(f"[webhook2] DEBUG - Message saved to database: {message_id}")

        # Broadcast to WebSocket for real-time UI updates
        try:
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": message_type,
                "message": body_text,
                "timestamp": timestamp.isoformat(),
                "message_id": message_id,
                "customer_name": sender_name,
                "customer_id": str(customer.id),
                "organization_id": str(organization_id) if organization_id else None,
                "source": "webhook2"
            })
            print(f"[webhook2] DEBUG - Message broadcasted to WebSocket: {message_id}")
        except Exception as e:
            print(f"[webhook2] WARNING - WebSocket broadcast failed: {e}")

        return {"status": "ok", "message_id": message_id}

    except Exception as e:
        # Log error with raw data
        if raw_str:
            log_webhook(f"ERROR: {str(e)}\nRAW: {raw_str}", "webhook2_error")
        print("[webhook2] ERROR:", e)
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}


@router2.get("")
async def verify_webhook2(request: Request):
    # No verify token required - accept all verification requests
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and challenge:
        print("[webhook2] VERIFIED")
        return PlainTextResponse(content=challenge)

    # Return simple OK for any other GET request
    return {"status": "webhook2 is active"}


@router2.get("/logs")
async def get_webhook2_logs(limit: int = 20):
    """View recent webhook2 logs from browser"""
    try:
        log_dir = "webhook_logs"
        if not os.path.exists(log_dir):
            return {"logs": [], "message": "No logs folder yet"}

        # Include both normal logs and error logs
        files = [f for f in os.listdir(log_dir) if f.startswith("webhook2")]
        files.sort(reverse=True)
        files = files[:limit]

        logs = []
        for filename in files:
            filepath = os.path.join(log_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    try:
                        content = json.loads(content)
                    except:
                        pass  # Keep as string if not JSON
                    logs.append({
                        "file": filename,
                        "data": content
                    })
            except Exception as e:
                logs.append({"file": filename, "error": str(e)})

        return {"total": len(logs), "logs": logs}
    except Exception as e:
        return {"error": str(e)}


# NOTE: WebSocket endpoint removed - webhook2 broadcasts through the shared
# /ws/channel endpoint via the same manager instance from utils.ws_manager.
# This avoids nginx configuration issues and keeps all real-time messages
# flowing through a single WebSocket connection.


# =============================================================================
# WEBHOOK2 SEND MESSAGE (Standard WhatsApp API - Organization-based)
# =============================================================================

import csv
import io
import mimetypes
import tempfile
import subprocess
from pathlib import Path

def _coerce_float(value: Optional[str]) -> Optional[float]:
    """Coerce string to float, return None if invalid"""
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
            if src_path and os.path.exists(src_path):
                os.remove(src_path)
        except Exception:
            pass
        try:
            if dst_path and os.path.exists(dst_path):
                os.remove(dst_path)
        except Exception:
            pass

@router2.post("/send-message")
async def send_message_webhook2(
    peer: str = Form(...),
    wa_id: str = Form(...),
    type: Literal[
        "text", "template", "image", "document",
        "audio", "video", "interactive", "location", "flow"
    ] = Form(...),

    # Common
    body: Optional[str] = Form(None),
    language: Optional[str] = Form("en_US"),
    file: Optional[UploadFile] = File(None),

    # Location
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    location_name: Optional[str] = Form(None),
    location_address: Optional[str] = Form(None),

    # Template
    template_name: Optional[str] = Form(None),
    template_params: Optional[str] = Form(None),
    template_button_params: Optional[str] = Form(None),
    template_button_index: Optional[str] = Form("0"),
    template_button_sub_type: Optional[str] = Form("url"),
    template_media_id: Optional[str] = Form(None),
    template_header_params: Optional[int] = Form(None),
    template_body_expected: Optional[int] = Form(None),
    template_enforce_count: Optional[bool] = Form(False),

    # Media (legacy support - prefer file upload)
    media_url: Optional[str] = Form(None),

    # Interactive
    interactive_data: Optional[str] = Form(None),

    # Flow-specific
    flow_id: Optional[str] = Form(None),
    flow_cta: Optional[str] = Form("Provide Address"),
    flow_token: Optional[str] = Form(None),
    flow_payload_json: Optional[str] = Form(None),

    db: Session = Depends(get_db)
):
    """
    Send message via WhatsApp API (webhook2 - organization-based)
    
    Matches the structure of /secret/send-message from whatsapp_controller.py for consistency.
    Uses organization-based phone number lookup from whatsapp_numbers table.
    
    NOTE: Text messages only work within 24-hour window after customer messages you.
    Use templates to initiate conversations.
    """
    try:
        # Get WhatsApp config for this peer (looks up from database)
        whatsapp_config = get_whatsapp_config_by_peer(db, peer)
        
        headers = {
            "Authorization": f"Bearer {whatsapp_config['token']}"
        }
        
        WHATSAPP_API_URL = whatsapp_config['api_url']
        MEDIA_URL = whatsapp_config['media_url']
        phone_number_id = whatsapp_config['phone_number_id']
        from_wa_id = peer  # sender changes based on peer
        
        media_id = None
        caption = None
        filename = None
        mime_type = None
        uploaded_filename = None
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
            if not body:
                raise HTTPException(status_code=400, detail="Text body required")
            payload["text"] = {"body": body, "preview_url": False}
            print(payload)
        # ---------------- Image Message ----------------
        elif type == "image":
            if not media_id and not media_url and not template_media_id:
                raise HTTPException(status_code=400, detail="Image upload or media_url is required for image messages")
            if media_id:
                payload["image"] = {"id": media_id, "caption": body or ""}
            else:
                # Use URL (legacy support)
                payload["image"] = {"link": media_url or template_media_id}
                if body:
                    payload["image"]["caption"] = body

        # ---------------- Document Message ----------------
        elif type == "document":
            if not media_id and not media_url:
                raise HTTPException(status_code=400, detail="Document upload or media_url is required for document messages")
            doc_name = uploaded_filename or (file.filename if file else None)
            if media_id:
                payload["document"] = {"id": media_id, "caption": body or "", "filename": doc_name}
            else:
                payload["document"] = {"link": media_url}
                if body:
                    payload["document"]["caption"] = body

        # ---------------- Video Message ----------------
        elif type == "video":
            if not media_id and not media_url:
                raise HTTPException(status_code=400, detail="Video upload or media_url is required for video messages")
            if media_id:
                payload["video"] = {"id": media_id}
                if body:
                    payload["video"]["caption"] = body
            else:
                payload["video"] = {"link": media_url}
                if body:
                    payload["video"]["caption"] = body

        # ---------------- Audio Message ----------------
        elif type == "audio":
            if not media_id and not media_url:
                raise HTTPException(status_code=400, detail="Audio upload or media_url is required for audio messages")
            if media_id:
                payload["audio"] = {"id": media_id}
            else:
                payload["audio"] = {"link": media_url}
            effective_media_id = media_id

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

        # ---------------- Interactive Message ----------------
        elif type == "interactive":
            if not interactive_data:
                raise HTTPException(status_code=400, detail="interactive_data JSON is required")
            try:
                interactive = json.loads(interactive_data)
                payload["interactive"] = interactive
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid interactive_data JSON")

        # ---------------- Template Message ----------------
        elif type == "template":
            if not template_name:
                raise HTTPException(status_code=400, detail="template_name is required")

            components = []

            # Parse template_params (CSV format)
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

            # Button parameters
            if template_button_params:
                try:
                    reader = csv.reader(io.StringIO(template_button_params))
                    row = next(reader, [])
                    btn_param_list = [p.strip() for p in row]
                except Exception:
                    btn_param_list = [p.strip() for p in template_button_params.split(",") if p]

                if btn_param_list:
                    try:
                        button_index_int = int(str(template_button_index or "0").strip())
                    except (ValueError, AttributeError):
                        button_index_int = 0

                    components.append({
                        "type": "button",
                        "sub_type": str(template_button_sub_type or "url"),
                        "index": button_index_int,
                        "parameters": [{"type": "text", "text": v} for v in btn_param_list]
                    })

            # Image Header (from URL or media ID)
            effective_media_id = template_media_id or media_id
            if effective_media_id:
                is_url = effective_media_id.startswith("http://") or effective_media_id.startswith("https://")
                is_resumable_handle = effective_media_id.startswith("4:") and len(effective_media_id) > 50

                if is_url:
                    image_param = {"link": effective_media_id}
                elif is_resumable_handle:
                    image_param = {"id": effective_media_id}
                else:
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
                "language": {"code": language or "en_US"},
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
                "header": {"type": "text", "text": "📍 Address Collection"},
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

        print(f"[webhook2] Sending {type} from {peer} (phone_id: {phone_number_id}) to {wa_id}")
        print(f"[webhook2] API URL: {WHATSAPP_API_URL}")
        print(f"[webhook2] Payload: {json.dumps(payload, indent=2)}")

        # Send to WhatsApp API
        res = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers={**headers, "Content-Type": "application/json"}
        )

        if res.status_code != 200:
            error_detail = res.text
            try:
                error_json = res.json()
                error_detail = json.dumps(error_json, indent=2)
            except:
                pass
            raise HTTPException(status_code=500, detail=f"Failed to send message: {error_detail}")

        response_data = res.json()
        message_id = response_data.get("messages", [{}])[0].get("id", f"out_{datetime.now().timestamp()}")
        print(f"[webhook2] Response: {res.status_code} - Message ID: {message_id}")

        # Save outgoing message to database
        try:
            # Look up organization from phone_number_id
            organization_id = None
            try:
                from services.whatsapp_number_service import get_organization_by_phone_id
                organization = get_organization_by_phone_id(db, phone_number_id)
                if organization:
                    organization_id = organization.id
            except Exception as e:
                print(f"[webhook2] WARNING - Could not look up organization: {e}")

            customer_data = CustomerCreate(wa_id=wa_id, name="")
            customer = customer_service.get_or_create_customer(db, customer_data, organization_id=organization_id)

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
            )
            message_service.create_message(db, message_data)
            db.commit()

            # Broadcast to WebSocket
            await manager.broadcast({
                "from": from_wa_id,
                "to": wa_id,
                "type": type,
                "message": body or "",
                "timestamp": datetime.now().isoformat(),
                "message_id": message_id,
                "customer_id": str(customer.id),
                "organization_id": str(organization_id) if organization_id else None,
                "media_id": effective_media_id,
                "caption": body if type in ["image", "document", "video"] else None,
                "filename": uploaded_filename if file else None,
                "mime_type": mime_type,
                "source": "webhook2"
            })

            print(f"[webhook2] Message saved and broadcasted: {message_id}")
        except Exception as e:
            print(f"[webhook2] WARNING - Could not save message: {e}")
            import traceback
            traceback.print_exc()

        return {
            "status": "success",
            "message_id": message_id,
            "response": response_data,
            "media_id": effective_media_id,
            "mime_type": mime_type,
            "filename": uploaded_filename
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[webhook2] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}


@router2.get("/numbers")
async def get_organization_numbers(
    organization_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get active WhatsApp numbers filtered by the logged-in user's organization.
    Used by frontend to populate the "All Numbers" dropdown filter.
    
    - For regular users: Returns only numbers from their organization
    - For SUPER_ADMIN: Returns all active numbers (or filtered by organization_id if provided)
    
    Args:
        organization_id: Optional UUID string to filter numbers by organization (only for SUPER_ADMIN).
                        For regular users, this parameter is ignored and their organization is used automatically.
    """
    try:
        from models.models import WhatsAppNumber
        from uuid import UUID
        from utils.organization_filter import get_user_organization_id
        
        # Get user's organization_id
        user_org_id = get_user_organization_id(current_user)
        
        # Query active numbers
        query = db.query(WhatsAppNumber).filter(WhatsAppNumber.is_active == True)
        
        # Filter by organization
        # SUPER_ADMIN can optionally filter by organization_id parameter, otherwise sees all
        # Regular users always see only their organization's numbers
        is_super_admin = current_user.role == 'SUPER_ADMIN' or (current_user.role_obj and current_user.role_obj.name == 'SUPER_ADMIN')
        
        if is_super_admin:
            # Super admin: use organization_id parameter if provided, otherwise show all
            if organization_id:
                try:
                    org_uuid = UUID(organization_id)
                    query = query.filter(WhatsAppNumber.organization_id == org_uuid)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid organization_id format")
            # If no organization_id provided, super admin sees all numbers
        else:
            # Regular users: always filter by their organization
            if user_org_id:
                query = query.filter(WhatsAppNumber.organization_id == user_org_id)
            else:
                # User has no organization - return empty list
                query = query.filter(False)
        
        numbers = query.order_by(WhatsAppNumber.display_number.asc()).all()

        return {
            "items": [
                {
                    "phone_number_id": num.phone_number_id,
                    "display_number": num.display_number or num.phone_number_id,
                    "organization_id": str(num.organization_id) if num.organization_id else None,
                    "organization_name": num.organization.name if num.organization else None,
                    "is_active": num.is_active
                }
                for num in numbers
            ],
            "total": len(numbers)
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[webhook2] ERROR getting numbers: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router2.post("/send-template")
async def send_template_webhook2(
    peer: str = Form(...),
    wa_id: str = Form(...),
    template_name: str = Form(...),
    language: str = Form("en_US"),
    components: Optional[str] = Form(None),  # JSON string
    db: Session = Depends(get_db)
):
    """
    Quick endpoint to send template messages via WhatsApp API (organization-based)

    Args:
        peer: The sender phone number (display_number or phone_number_id)
        wa_id: The recipient WhatsApp ID
        template_name: Name of the WhatsApp template
        language: Template language code (default: en_US)
        components: JSON string of template components
    """
    try:
        # Get WhatsApp config for this peer (looks up from database)
        whatsapp_config = get_whatsapp_config_by_peer(db, peer)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {whatsapp_config['token']}"
        }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language}
            }
        }

        if components:
            try:
                payload["template"]["components"] = json.loads(components)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid components JSON")

        print(f"[webhook2] Sending template '{template_name}' from {peer} (phone_id: {whatsapp_config['phone_number_id']}) to {wa_id}")
        print(f"[webhook2] Payload: {json.dumps(payload, indent=2)}")

        # Send to WhatsApp API
        res = requests.post(
            whatsapp_config['api_url'],
            headers=headers,
            json=payload
        )

        if res.status_code != 200:
            error_detail = res.text
            try:
                error_json = res.json()
                error_detail = json.dumps(error_json, indent=2)
            except:
                pass
            raise HTTPException(status_code=500, detail=f"Failed to send template: {error_detail}")

        response_data = res.json()
        message_id = response_data.get("messages", [{}])[0].get("id")
        print(f"[webhook2] WhatsApp API response: {res.status_code} - Message ID: {message_id}")

        return {
            "status": "success",
            "message_id": message_id,
            "response": response_data
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[webhook2] ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
