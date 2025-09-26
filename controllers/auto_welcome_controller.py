from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
import os
import requests

from database.db import get_db
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from services import customer_service, message_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from starlette.responses import PlainTextResponse
from controllers.web_socket import VERIFY_TOKEN
from utils.ws_manager import manager
from utils.whatsapp import send_message_to_waid
import re


router = APIRouter()


def _send_template(wa_id: str, template_name: str, access_token: str, phone_id: str, components: list | None = None, lang_code: str | None = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    effective_lang = lang_code or os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": effective_lang}
        }
    }
    # Normalize components: treat empty list as None
    if components is not None and isinstance(components, list) and len(components) == 0:
        components = None
    if components is not None:
        payload["template"]["components"] = components
    try:
        # Safe debug: show whether components included and a compact preview
        has_components = "components" in payload.get("template", {})
        comp_preview = None
        if has_components:
            try:
                comp_preview = [{"type": c.get("type"), "num_params": len((c.get("parameters") or []))} for c in payload["template"]["components"]]
            except Exception:
                comp_preview = "unavailable"
        print(f"[_send_template] name={template_name} lang={effective_lang} has_components={has_components} components_preview={comp_preview}")
    except Exception:
        pass
    return requests.post(get_messages_url(phone_id), headers=headers, json=payload)


def _verify_contact_with_openai(text: str) -> dict:
    """Use OpenAI to extract and validate name and phone number from free text.
    Returns dict: { valid: bool, name: str|None, phone: str|None, reason: str|None }
    Fallback to regex-only if OPENAI_API_KEY missing or API fails.
    """
    # Enhanced regex extraction for Indian phone numbers
    # Look for +91 followed by 10 digits, or just 10 digits
    phone_patterns = [
        r"\+91[-\s]?(\d{10})",  # +91 followed by 10 digits
        r"\b(\d{10})\b"  # Just 10 digits
    ]
    
    extracted_phone = None
    for pattern in phone_patterns:
        phone_match = re.search(pattern, text)
        if phone_match:
            extracted_phone = phone_match.group(1) if phone_match.groups() else phone_match.group(0)
            # Ensure it's exactly 10 digits
            if len(extracted_phone) == 10 and extracted_phone.isdigit():
                break
            else:
                extracted_phone = None
    
    # naive name guess: take words without digits, first 2-3 tokens
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", text) if len(w) > 1]
    extracted_name = " ".join(words[:3]) if words else None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "valid": bool(extracted_phone and extracted_name),
            "name": extracted_name,
            "phone": f"+91{extracted_phone}" if extracted_phone else None,
            "reason": "OPENAI_API_KEY not set; regex validation used"
        }

    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = (
            "You are a strict validator for Indian contact information. Extract a human name and Indian 10-digit phone number from the text. "
            "Phone number requirements: Must be exactly 10 digits, can have +91 prefix or not, but should be a valid Indian mobile number. "
            "Name requirements: Must be a plausible human name (at least 2 words, no numbers). "
            "Return ONLY strict JSON with keys: valid (boolean), name (string|null), phone (string|null), reason (string). "
            "valid must be true only if both a plausible name is present AND phone is exactly 10 digits (Indian format). "
            "Phone should be returned as +91XXXXXXXXXX format (10 digits after +91)."
        )
        data = {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ]
        }
        resp = requests.post(url, headers=headers, json=data, timeout=20)
        if resp.status_code != 200:
            # Format phone number to ensure +91 prefix
            phone = extracted_phone
            if phone and not phone.startswith("+91"):
                if phone.isdigit() and len(phone) == 10:
                    phone = f"+91{phone}"
                elif phone.startswith("91") and len(phone) == 12:
                    phone = f"+{phone}"
            
            return {
                "valid": bool(extracted_phone and extracted_name),
                "name": extracted_name,
                "phone": phone,
                "reason": f"OpenAI error {resp.status_code}: {resp.text[:200]}"
            }
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = {}
        try:
            import json as _json
            parsed = _json.loads(content)
        except Exception:
            parsed = {}
        # Format phone number to ensure +91 prefix
        phone = parsed.get("phone") or extracted_phone
        if phone and not phone.startswith("+91"):
            if phone.isdigit() and len(phone) == 10:
                phone = f"+91{phone}"
            elif phone.startswith("91") and len(phone) == 12:
                phone = f"+{phone}"
        
        return {
            "valid": bool(parsed.get("valid")),
            "name": parsed.get("name") or extracted_name,
            "phone": phone,
            "reason": parsed.get("reason") or "validated"
        }
    except Exception as e:
        # Format phone number to ensure +91 prefix
        phone = extracted_phone
        if phone and not phone.startswith("+91"):
            if phone.isdigit() and len(phone) == 10:
                phone = f"+91{phone}"
            elif phone.startswith("91") and len(phone) == 12:
                phone = f"+{phone}"
        
        return {
            "valid": bool(extracted_phone and extracted_name),
            "name": extracted_name,
            "phone": phone,
            "reason": f"OpenAI exception: {str(e)[:120]}"
        }


@router.post("/webhook")
async def whatsapp_auto_welcome_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        try:
            print("[auto_webhook] inbound body keys:", list(body.keys()))
        except Exception:
            pass
        value = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
        messages = value.get("messages") or []
        contacts = value.get("contacts") or []

        if not messages or not contacts:
            return {"status": "ignored"}

        message = messages[0]
        contact = contacts[0]

        wa_id = contact.get("wa_id") or message.get("from")
        from_wa_id = message.get("from")
        to_wa_id = value.get("metadata", {}).get("display_phone_number")
        timestamp = datetime.fromtimestamp(int(message.get("timestamp", datetime.now().timestamp())))
        message_type = message.get("type")
        message_id = message.get("id")
        body_text = (message.get(message_type, {}) or {}).get("body", "") if isinstance(message.get(message_type, {}), dict) else ""
        sender_name = (contact.get("profile") or {}).get("name") or ""

        # Normalize body text for consistent comparison
        def _normalize(txt: str) -> str:
            if not txt:
                return ""
            try:
                import re
                # replace fancy apostrophes/quotes with plain, remove non-letters/numbers/spaces
                txt = txt.replace("'", "'").replace(""", '"').replace(""", '"')
                txt = txt.lower().strip()
                txt = re.sub(r"\s+", " ", txt)
                return txt
            except Exception:
                return txt.lower().strip()

        normalized_body = _normalize(body_text)

        try:
            print(f"[auto_webhook] wa_id={wa_id} from={from_wa_id} to={to_wa_id} type={message_type} id={message_id}")
            print(f"[auto_webhook] raw body_text='{body_text}'")
        except Exception:
            pass

        # Ensure customer exists
        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Check if this is the first-ever message from this WA ID (before persisting current one)
        try:
            prior_messages = message_service.get_messages_by_wa_id(db, wa_id)
        except Exception:
            prior_messages = []

        # Persist inbound message minimally (so the rest of the system can see it), without touching ws flow
        try:
            inbound = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type=message_type,
                body=body_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, inbound)
            try:
                # Broadcast inbound to websocket clients
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": message_type if message_type else "text",
                    "message": body_text,
                    "timestamp": timestamp.isoformat()
                })
            except Exception:
                pass
        except Exception:
            pass

        # If user provided name and phone in free text, verify via OpenAI and notify
        # Check for phone number patterns or name keywords
        has_phone = re.search(r"\b\d{10}\b", normalized_body) or re.search(r"\+91", normalized_body)
        has_name_keywords = any(keyword in normalized_body for keyword in ["name", "i am", "my name", "call me"])
        
        print(f"[auto_webhook] DEBUG - message_type: {message_type}")
        print(f"[auto_webhook] DEBUG - normalized_body: '{normalized_body}'")
        print(f"[auto_webhook] DEBUG - has_phone: {has_phone}")
        print(f"[auto_webhook] DEBUG - has_name_keywords: {has_name_keywords}")
        
        if message_type == "text" and (has_phone or has_name_keywords):
            print(f"[auto_webhook] DEBUG - Triggering contact verification")
            verification = _verify_contact_with_openai(body_text)
            print(f"[auto_webhook] DEBUG - Verification result: {verification}")
            try:
                print(f"[auto_webhook] DEBUG - Broadcasting contact_verification to websocket")
                await manager.broadcast({
                    "from": to_wa_id,
                    "to": wa_id,
                    "type": "contact_verification",
                    "result": verification,
                    "timestamp": datetime.now().isoformat()
                })
                print(f"[auto_webhook] DEBUG - contact_verification broadcast successful")
            except Exception as e:
                print(f"[auto_webhook] DEBUG - contact_verification broadcast failed: {e}")
                pass
            # Inform user on WhatsApp
            try:
                if verification.get("valid"):
                    print(f"[auto_webhook] DEBUG - Verification valid, sending confirmation message")
                    await send_message_to_waid(wa_id, f"✅ Received details. Name: {verification.get('name')} | Phone: {verification.get('phone')}", db)
                    print(f"[auto_webhook] DEBUG - Confirmation message sent")
                    # Send mr_treatment template (with name param) and fallback to interactive buttons on failure
                    try:
                        print(f"[auto_webhook] DEBUG - Attempting to send mr_treatment template")
                        token_entry_btn = get_latest_token(db)
                        if token_entry_btn and token_entry_btn.token:
                            print(f"[auto_webhook] DEBUG - Token found, proceeding with template")
                            access_token_btn = token_entry_btn.token
                            phone_id_btn = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                            lang_code_btn = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                            name_param = verification.get('name') or sender_name or wa_id or "there"
                            components_btn = [{"type": "body", "parameters": [{"type": "text", "text": name_param}]}]
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template_attempt",
                                    "message": "Sending mr_treatment...",
                                    "params": {"body_param_1": name_param, "lang": lang_code_btn},
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception:
                                pass
                            resp_btn = _send_template(wa_id=wa_id, template_name="mr_treatment", access_token=token_entry_btn.token, phone_id=phone_id_btn, components=components_btn, lang_code=lang_code_btn)
                            print(f"[auto_webhook] DEBUG - Template response status: {resp_btn.status_code}")
                            if resp_btn.status_code == 200:
                                print(f"[auto_webhook] DEBUG - Template sent successfully")
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template",
                                        "message": "mr_treatment sent",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                            else:
                                # Fallback to interactive buttons
                                headers_btn = {"Authorization": f"Bearer {access_token_btn}", "Content-Type": "application/json"}
                                payload_btn = {
                                    "messaging_product": "whatsapp",
                                    "to": wa_id,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button",
                                        "body": {"text": "Please choose your area of concern:"},
                                        "action": {
                                            "buttons": [
                                                {"type": "reply", "reply": {"id": "skin", "title": "Skin"}},
                                                {"type": "reply", "reply": {"id": "hair", "title": "Hair"}},
                                                {"type": "reply", "reply": {"id": "body", "title": "Body"}}
                                            ]
                                        }
                                    }
                                }
                                requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "interactive",
                                        "message": "Please choose your area of concern:",
                                        "timestamp": datetime.now().isoformat(),
                                        "meta": {"kind": "buttons", "options": ["Skin", "Hair", "Body"]}
                                    })
                                except Exception:
                                    pass
                    except Exception:
                        pass
                else:
                    print(f"[auto_webhook] DEBUG - Verification not valid, sending error message")
                    await send_message_to_waid(wa_id, "❌ Please share a valid full name and a 10-digit phone number.", db)
                    print(f"[auto_webhook] DEBUG - Error message sent")
            except Exception:
                pass

        # Handle treatment selection replies (interactive button → list)
        if message_type == "interactive":
            interactive = message.get("interactive", {}) or {}
            i_type = interactive.get("type")
            if i_type == "button_reply":
                reply_id = (interactive.get("button_reply", {}) or {}).get("id", "").lower().strip()
                if reply_id in {"skin", "hair", "body"}:
                    try:
                        token_entry2 = get_latest_token(db)
                        if token_entry2 and token_entry2.token:
                            access_token2 = token_entry2.token
                            headers2 = {"Authorization": f"Bearer {access_token2}", "Content-Type": "application/json"}
                            phone_id2 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                            def list_rows(items):
                                return [{"id": f"{reply_id}:{i}", "title": title} for i, title in enumerate(items, start=1)]

                            if reply_id == "skin":
                                rows = list_rows(["Acne / Acne Scars", "Pigmentation & Uneven Skin Tone", "Anti-Aging & Skin Rejuvenation", "Laser Hair Removal", "Other Skin Concerns"])
                                section_title = "Skin"
                            elif reply_id == "hair":
                                rows = list_rows(["Hair Loss / Hair Fall", "Hair Transplant", "Dandruff & Scalp Care", "Other Hair Concerns"])
                                section_title = "Hair"
                            else:
                                rows = list_rows(["Weight Management", "Body Contouring", "Weight Loss", "Other Body Concerns"])
                                section_title = "Body"

                            payload_list = {
                                "messaging_product": "whatsapp",
                                "to": wa_id,
                                "type": "interactive",
                                "interactive": {
                                    "type": "list",
                                    "header": {"type": "text", "text": "Select a treatment"},
                                    "body": {"text": "Please choose one option:"},
                                    "action": {
                                        "button": "Choose",
                                        "sections": [{"title": section_title, "rows": rows}]
                                    }
                                }
                            }
                            requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "interactive",
                                    "message": "Please choose one option:",
                                    "timestamp": datetime.now().isoformat(),
                                    "meta": {"kind": "list", "section": section_title}
                                })
                            except Exception:
                                pass
                        return {"status": "list_sent", "message_id": message_id}
                    except Exception:
                        pass

        # Check if this is the prefill message to send mr_welcome_temp
        # Known wa.link prefill phrase variants
        allowed_variants = [
            _normalize("Hi, I'm interested in knowing more about your services. Please share details."),
            _normalize("Hi, I'm interested in knowing more about your services. Please share details."),
            _normalize("Hi I'm interested in knowing more about your services. Please share details."),
        ]
        try:
            print("[auto_webhook] normalized_body=", normalized_body)
            print("[auto_webhook] allowed_variants[0]=", allowed_variants[0])
        except Exception:
            pass
        
        # If this is the prefill message, send mr_welcome_temp and return
        if normalized_body in allowed_variants:
            print("[auto_webhook] Prefill message detected, sending mr_welcome_temp")
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                print("[auto_webhook] no WhatsApp token available")
                return {"status": "no_token"}

            access_token = token_entry.token
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
            lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
            
            # Prepare components to satisfy template params (expects 1 body param). We pass customer name.
            body_components = [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": (sender_name or wa_id or "there")}
                ]
            }]

            try:
                await manager.broadcast({
                    "from": to_wa_id,
                    "to": wa_id,
                    "type": "template_attempt",
                    "message": "Sending mr_welcome_temp...",
                    "params": {"body_param_1": (sender_name or wa_id or "there")},
                    "timestamp": datetime.now().isoformat()
                })
            except Exception:
                pass

            resp = _send_template(
                wa_id=wa_id,
                template_name="mr_welcome_temp",
                access_token=access_token,
                phone_id=phone_id,
                components=body_components,
                lang_code=lang_code
            )

            if resp.status_code == 200:
                try:
                    tpl_msg_id = resp.json()["messages"][0]["id"]
                    tpl_message = MessageCreate(
                        message_id=tpl_msg_id,
                        from_wa_id=to_wa_id,
                        to_wa_id=wa_id,
                        type="template",
                        body=f"mr_welcome_temp sent to {sender_name or wa_id}",
                        timestamp=datetime.now(),
                        customer_id=customer.id,
                    )
                    message_service.create_message(db, tpl_message)
                    try:
                        # Broadcast template send event to websocket clients
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template",
                            "message": f"mr_welcome_temp sent to {sender_name or wa_id}",
                            "timestamp": datetime.now().isoformat()
                        })
                    except Exception:
                        pass
                except Exception:
                    pass
                return {"status": "welcome_sent", "message_id": message_id}
            else:
                try:
                    print("[auto_webhook] mr_welcome_temp send failed:", resp.status_code, resp.text[:500])
                except Exception:
                    pass
                return {"status": "welcome_failed", "error": resp.text}
        
        # If not prefill message, continue with name/phone validation flow
        # (The name/phone validation logic is already handled above in the text message section)

    except Exception as e:
        try:
            print("[auto_webhook] exception:", str(e))
        except Exception:
            pass
        return {"status": "error", "error": str(e)}


@router.get("/webhook")
async def verify_auto_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)
    else:
        raise HTTPException(status_code=403)


