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
from pydantic import BaseModel

from database.db import get_db
from controllers.utils.debug_window import debug_webhook_payload
from services import customer_service, message_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from models.models import Message
from utils.ws_manager import manager

# =============================================================================
# CONFIG
# =============================================================================

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "oasis123")

# Alots.io Configuration for webhook2
# Map peer (display phone number) to phone_number_id and token
ALOTS_CONFIG = {
    "917416159696": {
        "phone_number_id": "916824348188229",
        "token": os.getenv("ALOTS_API_TOKEN", "c0b140ef-a10a-4d2c-a6b0-e5f65668551c"),
        "display_name": "Oasis Fertility"
    }
}

def get_alots_config(peer: str):
    """Get Alots.io API config for a peer number"""
    config = ALOTS_CONFIG.get(peer)
    if not config:
        raise HTTPException(status_code=400, detail=f"Invalid peer number: {peer}. Valid peers: {list(ALOTS_CONFIG.keys())}")
    return {
        "api_url": f"https://alots.io/v22.0/{config['phone_number_id']}/messages",
        "token": config["token"],
        "phone_number_id": config["phone_number_id"],
        "display_name": config.get("display_name", peer)
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


@router2.websocket("/channel")
async def webhook2_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket channel for webhook2 - receives real-time messages
    Connect to: wss://whatsapp.olivaclinic.com/webhook2/channel
    """
    await manager.connect(websocket)
    print("[webhook2] WebSocket client connected")
    try:
        while True:
            try:
                # Keep connection alive, receive any client messages (optional)
                data = await websocket.receive_text()
                # Echo back or handle client messages if needed
                if data:
                    print(f"[webhook2] WebSocket received from client: {data}")
            except WebSocketDisconnect:
                break
            except RuntimeError:
                break
            except Exception:
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
        print("[webhook2] WebSocket client disconnected")


# =============================================================================
# WEBHOOK2 SEND MESSAGE (Alots.io API)
# =============================================================================

class TemplateComponent(BaseModel):
    type: str
    parameters: List[dict] = []

class SendMessageRequest(BaseModel):
    wa_id: str
    type: Literal["text", "template", "image", "document", "audio", "video", "interactive"]
    body: Optional[str] = None
    template_name: Optional[str] = None
    template_language: Optional[str] = "en"
    template_components: Optional[List[dict]] = None
    media_url: Optional[str] = None
    media_caption: Optional[str] = None
    interactive_data: Optional[dict] = None


@router2.post("/send-message")
async def send_message_webhook2(
    peer: str = Form(...),
    wa_id: str = Form(...),
    type: Literal["text", "template", "image", "document", "audio", "video", "interactive"] = Form(...),
    body: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    template_language: Optional[str] = Form("en"),
    template_components: Optional[str] = Form(None),  # JSON string
    media_url: Optional[str] = Form(None),
    media_caption: Optional[str] = Form(None),
    interactive_data: Optional[str] = Form(None),  # JSON string
    db: Session = Depends(get_db)
):
    """
    Send message via Alots.io API (webhook2 account)

    Args:
        peer: The sender phone number (e.g., 917416159696)
        wa_id: The recipient WhatsApp ID
        type: Message type (text, template, image, etc.)

    Supports:
    - text: Simple text message
    - template: WhatsApp template message
    - image/document/audio/video: Media messages
    - interactive: Buttons/lists
    """
    try:
        # Get Alots.io config for this peer
        alots_config = get_alots_config(peer)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {alots_config['token']}"
        }

        # Build payload based on message type
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_id
        }

        if type == "text":
            if not body:
                raise HTTPException(status_code=400, detail="body is required for text messages")
            payload["type"] = "text"
            payload["text"] = {
                "preview_url": False,
                "body": body
            }

        elif type == "template":
            if not template_name:
                raise HTTPException(status_code=400, detail="template_name is required for template messages")
            payload["type"] = "template"
            payload["template"] = {
                "name": template_name,
                "language": {"code": template_language or "en"}
            }
            if template_components:
                try:
                    components = json.loads(template_components)
                    payload["template"]["components"] = components
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail="Invalid template_components JSON")

        elif type in ["image", "document", "audio", "video"]:
            if not media_url:
                raise HTTPException(status_code=400, detail=f"media_url is required for {type} messages")
            payload["type"] = type
            payload[type] = {"link": media_url}
            if media_caption and type in ["image", "document", "video"]:
                payload[type]["caption"] = media_caption

        elif type == "interactive":
            if not interactive_data:
                raise HTTPException(status_code=400, detail="interactive_data is required for interactive messages")
            try:
                interactive = json.loads(interactive_data)
                payload["type"] = "interactive"
                payload["interactive"] = interactive
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid interactive_data JSON")

        print(f"[webhook2] Sending message from {peer} to {wa_id}")
        print(f"[webhook2] API URL: {alots_config['api_url']}")
        print(f"[webhook2] Payload: {json.dumps(payload, indent=2)}")

        # Send to Alots.io API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                alots_config['api_url'],
                headers=headers,
                json=payload,
                timeout=30.0
            )

        response_data = response.json()
        print(f"[webhook2] Alots.io response: {response.status_code} - {response_data}")

        if response.status_code >= 400:
            return {
                "status": "failed",
                "error": response_data,
                "status_code": response.status_code
            }

        # Save outgoing message to database
        try:
            message_id = response_data.get("messages", [{}])[0].get("id", f"out_{datetime.now().timestamp()}")
            customer = customer_service.get_customer_by_wa_id(db, wa_id)
            if customer:
                outgoing_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=peer,
                    to_wa_id=wa_id,
                    type=type,
                    body=body or template_name or media_caption or f"[{type}]",
                    timestamp=datetime.now(),
                    customer_id=customer.id
                )
                message_service.create_message(db, outgoing_message)
                db.commit()
                print(f"[webhook2] Outgoing message saved: {message_id}")
        except Exception as e:
            print(f"[webhook2] WARNING - Could not save outgoing message: {e}")

        return {
            "status": "success",
            "message_id": response_data.get("messages", [{}])[0].get("id"),
            "response": response_data
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[webhook2] ERROR sending message: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router2.post("/send-template")
async def send_template_webhook2(
    peer: str = Form(...),
    wa_id: str = Form(...),
    template_name: str = Form(...),
    language: str = Form("en"),
    components: Optional[str] = Form(None),  # JSON string
    db: Session = Depends(get_db)
):
    """
    Quick endpoint to send template messages via Alots.io

    Args:
        peer: The sender phone number (e.g., 917416159696)
        wa_id: The recipient WhatsApp ID
        template_name: Name of the WhatsApp template
        language: Template language code (default: en)
        components: JSON string of template components
    """
    try:
        # Get Alots.io config for this peer
        alots_config = get_alots_config(peer)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {alots_config['token']}"
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

        print(f"[webhook2] Sending template '{template_name}' from {peer} to {wa_id}")
        print(f"[webhook2] Payload: {json.dumps(payload, indent=2)}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                alots_config['api_url'],
                headers=headers,
                json=payload,
                timeout=30.0
            )

        response_data = response.json()
        print(f"[webhook2] Alots.io response: {response.status_code} - {response_data}")

        if response.status_code >= 400:
            return {"status": "failed", "error": response_data}

        return {
            "status": "success",
            "message_id": response_data.get("messages", [{}])[0].get("id"),
            "response": response_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
