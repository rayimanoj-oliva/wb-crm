from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
import os
import requests

from database.db import get_db
from services.whatsapp_service import get_latest_token
from marketing.whatsapp_numbers import get_number_config
from config.constants import get_messages_url
from services import customer_service, message_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from starlette.responses import PlainTextResponse
from controllers.web_socket import VERIFY_TOKEN
from utils.ws_manager import manager
from services.followup_service import mark_customer_replied
from services.followup_service import schedule_next_followup
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
        print(f"[_send_template] phone_id={phone_id} name={template_name} lang={effective_lang} has_components={has_components} components_preview={comp_preview}")
    except Exception:
        pass
    try:
        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        # Detailed debug for 200 and non-200
        preview = None
        try:
            j = resp.json()
            preview = {
                "status": resp.status_code,
                "message_ids": [m.get("id") for m in j.get("messages", [])] if isinstance(j, dict) else None,
                "error": j.get("error", {}).get("message") if isinstance(j, dict) else None,
            }
        except Exception:
            preview = {"status": resp.status_code, "text": (resp.text[:300] if isinstance(resp.text, str) else str(resp.text))}
        print(f"[_send_template] result phone_id={phone_id} name={template_name} preview={preview}")
        return resp
    except Exception as e:
        print(f"[_send_template] exception for phone_id={phone_id} name={template_name}: {e}")
        raise


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

    # Enforce minimum 3 alphabetic characters in the name (letters only)
    def _name_meets_min_chars(name: str | None) -> bool:
        if not isinstance(name, str):
            return False
        letters_only = re.sub(r"[^A-Za-z]", "", name)
        return len(letters_only) >= 3

    # Heuristic to check if a string resembles a plausible human name
    def _looks_like_human_name(name: str | None) -> bool:
        if not isinstance(name, str):
            return False
        candidate = name.strip()
        if not candidate:
            return False
        # Reject if contains digits or emoji-like non-word chars (besides space, hyphen, apostrophe)
        if re.search(r"\d", candidate):
            return False
        if re.search(r"[\u2600-\u27BF\u1F300-\u1F6FF\u1F900-\u1F9FF]", candidate):  # basic emoji blocks
            return False
        # Allow letters, spaces, hyphens, apostrophes only
        if re.search(r"[^A-Za-z\- '\s]", candidate):
            return False
        letters_only = re.sub(r"[^A-Za-z]", "", candidate)
        # Minimum length guard
        if len(letters_only) < 3:
            return False
        # Must contain at least one vowel and one consonant
        if not re.search(r"[AEIOUaeiou]", letters_only):
            return False
        if not re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only):
            return False
        # Disallow all same character or long repeats
        if len(set(letters_only.lower())) == 1:
            return False
        if re.search(r"(.)\1{3,}", letters_only, flags=re.IGNORECASE):
            return False
        # Reject very long consonant clusters (likely gibberish)
        if re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]{5,}", letters_only):
            return False
        # Token structure: prefer 2 tokens of >=2 chars, or single token >=4 chars
        tokens = [t for t in re.findall(r"[A-Za-z][A-Za-z\-']+", candidate)]
        if len(tokens) >= 2:
            if any(len(re.sub(r"[^A-Za-z]", "", t)) < 2 for t in tokens[:2]):
                return False
        else:
            if len(letters_only) < 4:
                return False
        # Common non-name placeholders/brand terms
        blacklist = {
            "test", "testing", "asdf", "qwerty", "user", "customer", "name", "unknown", "oliva", "oliva clinic", "clinic",
            "asd", "sdf", "dfg", "qwe", "zxc", "sdfhj", "qwert", "qwertyui", "abc", "abcd"
        }
        if candidate.strip().lower() in blacklist:
            return False
        # Looks acceptable
        return True

    # Normalize any phone-like string to +91XXXXXXXXXX (exactly 10 digits after +91)
    def _normalize_phone_str(phone_str: str | None) -> str | None:
        if not isinstance(phone_str, str):
            return None
        digits = re.sub(r"\D", "", phone_str)
        if len(digits) < 10:
            return None
        last10 = digits[-10:]
        if len(last10) != 10:
            return None
        return f"+91{last10}"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        normalized_phone = _normalize_phone_str(extracted_phone or "") if extracted_phone else None
        is_valid = bool(normalized_phone and _name_meets_min_chars(extracted_name) and _looks_like_human_name(extracted_name))
        return {
            "valid": is_valid,
            "name": extracted_name,
            "phone": normalized_phone,
            "reason": "OPENAI_API_KEY not set; regex validation used"
        }

    try:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = (
            "You are a strict validator for Indian contact information. Extract a human name and Indian 10-digit phone number from the text. "
            "Phone number requirements: Must be exactly 10 digits, can have +91 prefix or not, but should be a valid Indian mobile number. "
            "Name requirements: Must be a plausible human name with at least 3 alphabetic characters total (letters only count), contain vowels, avoid gibberish (e.g., 'asd', 'sdfhj'), preferably 2 words, and no numbers. "
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
            phone = _normalize_phone_str(extracted_phone or "") if extracted_phone else None
            is_valid = bool(phone and _name_meets_min_chars(extracted_name) and _looks_like_human_name(extracted_name))
            return {
                "valid": is_valid,
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
        # Normalize phone consistently to +91XXXXXXXXXX
        phone = _normalize_phone_str(parsed.get("phone")) or _normalize_phone_str(extracted_phone or "")
        
        # Enforce the 3-character minimum even if model marks valid
        parsed_name = parsed.get("name") or extracted_name
        valid_flag = bool(parsed.get("valid")) and _name_meets_min_chars(parsed_name) and _looks_like_human_name(parsed_name)
        return {
            "valid": valid_flag,
            "name": parsed_name,
            "phone": phone,
            "reason": parsed.get("reason") or ("validated" if valid_flag else "name not plausible or too short (<3 letters)")
        }
    except Exception as e:
        phone = _normalize_phone_str(extracted_phone or "") if extracted_phone else None
        is_valid = bool(phone and _name_meets_min_chars(extracted_name) and _looks_like_human_name(extracted_name))
        return {
            "valid": is_valid,
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
        phone_id_meta = (value.get("metadata", {}) or {}).get("phone_number_id")

        # Resolve credentials based on phone_number_id mapping (multi-number support)
        def _resolve_credentials():
            cfg = get_number_config(str(phone_id_meta)) if phone_id_meta else None
            if cfg and cfg.get("token"):
                return cfg.get("token"), str(phone_id_meta)
            token_entry = get_latest_token(db)
            if token_entry and token_entry.token:
                return token_entry.token, os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
            return None, None
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
            # Mark customer replied and clear any pending follow-up
            try:
                mark_customer_replied(db, customer_id=customer.id)
            except Exception:
                pass
            db.commit()  # Explicitly commit the transaction
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
        
        # Only validate contact details when we're explicitly awaiting them (after confirm_no)
        waiting_details = False
        try:
            from controllers.web_socket import lead_appointment_state as _lead_state  # type: ignore
            waiting_details = ((_lead_state.get(wa_id) or {}).get("waiting_for_user_details") is True)
        except Exception:
            waiting_details = False

        if message_type == "text" and waiting_details and (has_phone or has_name_keywords):
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
                    # After successful details, proceed to city selection (treatment flow)
                    try:
                        from controllers.components.lead_appointment_flow.city_selection import send_city_selection  # type: ignore
                        await send_city_selection(db, wa_id=wa_id)
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
                        access_token2, phone_id2 = _resolve_credentials()
                        if access_token2:
                            headers2 = {"Authorization": f"Bearer {access_token2}", "Content-Type": "application/json"}

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

        # Check if this is the prefill message to send mr_welcome
        # Known wa.link prefill phrase variants + simple greeting triggers
        allowed_variants = [
            _normalize("Hi, I'm interested in knowing more about your services. Please share details."),
            _normalize("Hi, I'm interested in knowing more about your services. Please share details."),
            _normalize("Hi I'm interested in knowing more about your services. Please share details."),
        ]
        import re as _re_hi
        greeting_match = bool(_re_hi.fullmatch(r"\s*(hi|hello|hlo)[.!]?\s*", normalized_body or ""))
        try:
            print("[auto_webhook] normalized_body=", normalized_body)
            print("[auto_webhook] allowed_variants[0]=", allowed_variants[0])
        except Exception:
            pass

        # If this is the prefill message OR a simple greeting, send mr_welcome and return
        if (normalized_body in allowed_variants) or greeting_match:
            # Idempotency: skip if treatment flow already sent welcome
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                st_w = appointment_state.get(wa_id) or {}
                if bool(st_w.get("mr_welcome_sent")):
                    return {"status": "skipped", "reason": "mr_welcome_already_sent"}
                # also short-circuit if a send started very recently
                from datetime import datetime, timedelta
                ts_str = st_w.get("mr_welcome_sending_ts")
                ts_obj = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else None
                if ts_obj and (datetime.utcnow() - ts_obj) < timedelta(seconds=10):
                    return {"status": "skipped", "reason": "mr_welcome_in_progress"}
                st_w["mr_welcome_sending_ts"] = datetime.utcnow().isoformat()
                appointment_state[wa_id] = st_w
            except Exception:
                pass
            print("[auto_webhook] Prefill message detected, sending mr_welcome")
        access_token, phone_id = _resolve_credentials()
        if not access_token:
            print("[auto_webhook] no WhatsApp token available")
            return {"status": "no_token"}

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
                "message": "Sending mr_welcome...",
                "params": {"body_param_1": (sender_name or wa_id or "there")},
                "timestamp": datetime.now().isoformat()
            })
        except Exception:
            pass

        resp = _send_template(
            wa_id=wa_id,
            template_name="mr_welcome",
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
                    body=f"mr_welcome sent to {sender_name or wa_id}",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                message_service.create_message(db, tpl_message)
                db.commit()  # Explicitly commit the transaction
                # Schedule follow-up 1 window only for mr_welcome
                try:
                    from services.customer_service import get_customer_record_by_wa_id as _get_c
                    from services.followup_service import FOLLOW_UP_1_DELAY_MINUTES
                    cust = _get_c(db, wa_id)
                    if cust:
                        schedule_next_followup(db, customer_id=cust.id, delay_minutes=FOLLOW_UP_1_DELAY_MINUTES, stage_label="mr_welcome_sent")
                except Exception:
                    pass
                try:
                    # Broadcast template send event to websocket clients
                    await manager.broadcast({
                        "from": to_wa_id,
                        "to": wa_id,
                        "type": "template",
                        "message": f"mr_welcome sent to {sender_name or wa_id}",
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception:
                    pass
            except Exception:
                pass
            # After mr_welcome: ask name/phone confirmation, then proceed to city → treatment
            try:
                # Mark treatment flow context for subsequent steps
                from controllers.web_socket import appointment_state  # type: ignore
                st = appointment_state.get(wa_id) or {}
                st["flow_context"] = "treatment"
                st["from_treatment_flow"] = True
                st["mr_welcome_sent"] = True
                appointment_state[wa_id] = st
            except Exception:
                pass

            # Send name/phone confirmation
            try:
                from services.customer_service import get_customer_record_by_wa_id
                customer_rec = get_customer_record_by_wa_id(db, wa_id)
                display_name = (customer_rec.name.strip() if customer_rec and isinstance(customer_rec.name, str) else None) or "there"
                try:
                    import re as _re
                    digits = _re.sub(r"\D", "", wa_id)
                    last10 = digits[-10:] if len(digits) >= 10 else None
                    display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
                except Exception:
                    display_phone = wa_id

                confirm_msg = (
                    f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*"
                )
                # Send confirmation via the SAME phone_number_id as mr_welcome
                await send_message_to_waid(wa_id, confirm_msg, db, phone_id_hint=str(phone_id))

                access_token_btn, phone_id_btn = _resolve_credentials()
                if access_token_btn:
                    headers_btn = {"Authorization": f"Bearer {access_token_btn}", "Content-Type": "application/json"}
                    payload_btn = {
                        "messaging_product": "whatsapp",
                        "to": wa_id,
                        "type": "interactive",
                        "interactive": {
                            "type": "button",
                            "body": {"text": "Are your name and contact number correct? "},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes"}},
                                    {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}},
                                ]
                            },
                        },
                    }
                    try:
                        _resp_btn = requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                        try:
                            print(f"[auto_webhook] DEBUG - confirm buttons sent phone_id={phone_id_btn} status={_resp_btn.status_code}")
                        except Exception:
                            pass
                    except Exception as _e_btn:
                        print(f"[auto_webhook] ERROR - confirm buttons post failed: {_e_btn}")
                    # Broadcast Yes/No buttons to websocket UI
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "interactive",
                            "message": "Are your name and contact number correct? ",
                            "timestamp": datetime.now().isoformat(),
                            "meta": {"kind": "buttons", "options": ["Yes", "No"]}
                        })
                    except Exception:
                        pass
            except Exception:
                pass
            return {"status": "welcome_and_confirm_sent", "message_id": message_id}
        else:
            try:
                    print("[auto_webhook] mr_welcome send failed:", resp.status_code, resp.text[:500])
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