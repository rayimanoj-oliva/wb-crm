from datetime import datetime
import os
import json

from fastapi import Request, APIRouter, HTTPException
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import Any
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from controllers.utils.debug_window import debug_webhook_payload

# =============================================================================
# CONFIG
# =============================================================================

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "oasis123")

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

# =============================================================================
# WEBHOOK 2
# =============================================================================

@router2.post("")
async def receive_webhook2(request: Request, db: Session = Depends(get_db)):
    try:
        raw = await request.body()
        raw_str = raw.decode("utf-8", errors="replace")
        body = json.loads(raw_str)

        log_webhook(raw_str, "webhook2")
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
            f"[webhook2] Message from {wa_id} ({sender}), "
            f"type={msg_type}, phone_id={phone_number_id}"
        )

        return {"status": "ok"}

    except Exception as e:
        print("[webhook2] ERROR:", e)
        return {"status": "failed", "error": str(e)}


@router2.get("")
async def verify_webhook2(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[webhook2] VERIFIED")
        return PlainTextResponse(content=challenge)

    raise HTTPException(status_code=403, detail="Forbidden")
