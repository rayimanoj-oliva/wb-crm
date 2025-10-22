"""
WhatsApp Cloud API Flow Integration
Handles native flow message generation, sending, and response processing
"""

import os
import json
import requests
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from database.db import get_db
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url

router = APIRouter()

# -------------------------------
# CONFIGURATION
# -------------------------------
FLOW_ID = "1314521433687006"  # ✅ Replace with your published Flow ID
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "367633743092037")
# In-memory cache (use Redis or DB in production)
flow_tokens: dict[str, str] = {}  # {wa_id: flow_token}


# -------------------------------
# FLOW INTEGRATION CLASS
# -------------------------------
class FlowIntegration:
    """Handles WhatsApp Flow message generation and processing"""

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------
    # STEP 1: Generate flow token
    # -------------------------------
    def generate_flow_token(self, wa_id: str) -> Optional[str]:
        """
        Generate a unique identifier (flow_token) locally.
        This replaces the unnecessary and unsupported API call.
        """
        try:
            new_token = f"TOKEN_{uuid.uuid4().hex}"
            flow_tokens[wa_id] = new_token
            print(f"✅ Generated flow_token for {wa_id}: {new_token}")
            return new_token
        except Exception as e:
            print("❌ Error generating flow_token:", str(e))
            return None

    def get_flow_token(self, wa_id: str) -> Optional[str]:
        return flow_tokens.get(wa_id)

    def clear_flow_token(self, wa_id: str):
        flow_tokens.pop(wa_id, None)

    # -------------------------------
    # STEP 2: Send flow message
    # -------------------------------
    async def send_flow_message(self, wa_id: str, flow_token: str) -> Dict[str, Any]:
        """Send flow message with valid flow_token"""
        try:
            token_entry = get_latest_token(self.db)
            if not token_entry or not token_entry.token:
                return {"success": False, "error": "No valid access token"}

            access_token = token_entry.token
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "interactive",
                "interactive": {
                    "type": "flow",
                    "header": {"type": "text", "text": "📍 Address Collection"},
                    "body": {
                        "text": "Please provide your delivery address using the form below."
                    },
                    "footer": {"text": "All fields are required for delivery."},
                    "action": {
                        "name": "flow",
                        "parameters": {
                            "flow_message_version": "3",
                            "flow_id": FLOW_ID,
                            "flow_cta": "Provide Address",
                            "flow_token": flow_token,
                        },
                    },
                },
            }

            response = requests.post(get_messages_url(PHONE_ID), headers=headers, json=payload)
            if response.status_code == 200:
                print(f"✅ Flow message sent to {wa_id}")
                return {"success": True, "response": response.json()}
            else:
                print(f"❌ Failed to send flow message: {response.text}")
                return {"success": False, "error": response.text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # -------------------------------
    # STEP 3: Process flow response
    # -------------------------------
    def process_flow_response(self, wa_id: str, response_json: str) -> Dict[str, Any]:
        """Extract user-submitted form data"""
        try:
            form_data = json.loads(response_json)

            # Detect placeholder issue
            if any("{{" in str(v) and "}}" in str(v) for v in form_data.values()):
                return {
                    "success": False,
                    "error": "Template placeholders detected — invalid or missing flow_token",
                    "data": form_data,
                }

            processed = {
                "wa_id": wa_id,
                "timestamp": datetime.now().isoformat(),
                "form_data": form_data,
            }

            return {"success": True, "data": processed}

        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON in response_json"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# -------------------------------
# INITIALIZE INTEGRATION
# -------------------------------
flow_integration = FlowIntegration(None)

# -------------------------------
# ROUTES
# -------------------------------
@router.post("/send-flow/{wa_id}")
async def send_flow_endpoint(wa_id: str, db: Session = Depends(get_db)):
    """Trigger sending a flow message to a WhatsApp user"""
    try:
        flow_integration.db = db
        flow_token = flow_integration.generate_flow_token(wa_id)
        if not flow_token:
            return {"status": "failed", "error": "Failed to generate flow_token"}

        result = await flow_integration.send_flow_message(wa_id, flow_token)
        if result["success"]:
            return {
                "status": "flow_sent",
                "wa_id": wa_id,
                "flow_token": flow_token,
                "message_id": result["response"]["messages"][0]["id"],
            }
        else:
            return {"status": "failed", "error": result["error"]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/token/{wa_id}")
async def generate_token_endpoint(wa_id: str, db: Session = Depends(get_db)):
    """Generate and return a new flow_token for a given wa_id (no message sent)."""
    flow_integration.db = db
    token = flow_integration.generate_flow_token(wa_id)
    if not token:
        return {"status": "failed", "error": "Failed to generate flow_token"}
    return {"status": "ok", "wa_id": wa_id, "flow_token": token}


@router.get("/token/{wa_id}")
async def get_token_endpoint(wa_id: str):
    """Fetch the currently stored flow_token for a given wa_id, if any."""
    token = flow_integration.get_flow_token(wa_id)
    if not token:
        return {"status": "not_found", "wa_id": wa_id}
    return {"status": "ok", "wa_id": wa_id, "flow_token": token}


@router.post("/process-response")
async def process_flow_response_endpoint(wa_id: str, response_json: str):
    """Process the user's Flow submission"""
    result = flow_integration.process_flow_response(wa_id, response_json)
    if result["success"]:
        flow_integration.clear_flow_token(wa_id)
        print(f"✅ Processed flow data for {wa_id}:", result["data"])
        return {"status": "processed", "data": result["data"]}
    else:
        print(f"❌ Flow processing failed for {wa_id}:", result["error"])
        return {"status": "failed", "error": result["error"]}


# Webhook handling removed from this module to avoid duplication; use existing webhook controller.
