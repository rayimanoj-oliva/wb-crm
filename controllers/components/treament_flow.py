from __future__ import annotations

from datetime import datetime
from typing import Optional, Any, Dict

import os
import re
import requests

from sqlalchemy.orm import Session

from schemas.message_schema import MessageCreate
from services import message_service
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from utils.ws_manager import manager
from utils.whatsapp import send_message_to_waid


async def run_treament_flow(
    db: Session,
    *,
    message_type: str,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    body_text: str,
    timestamp: datetime,
    customer: Any,
    wa_id: str,
    value: Dict[str, Any] | None,
    sender_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Encapsulates the text message auto-welcome validation and treatment template flow.

    Returns a status dict. This function is safe to call for any message type; it
    will act only when `message_type == "text"`.
    """

    handled_text = False

    # 1) Persist inbound text and broadcast to websocket
    if message_type == "text":
        try:
            inbound_msg = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="text",
                body=body_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, inbound_msg)
            try:
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": "text",
                    "message": body_text,
                    "timestamp": timestamp.isoformat(),
                })
            except Exception:
                pass
        except Exception:
            pass

        # 2) Normalize body text for consistent comparison
        def _normalize(txt: str) -> str:
            if not txt:
                return ""
            try:
                # Replace fancy apostrophes/quotes with plain, collapse spaces
                txt = txt.replace("'", "'").replace("“", '"').replace("”", '"')
                txt = txt.lower().strip()
                txt = re.sub(r"\s+", " ", txt)
                return txt
            except Exception:
                return txt.lower().strip()

        normalized_body = _normalize(body_text)

        # 3) Prefill detection for mr_welcome_temp
        prefill_regexes = [
            r"^hi,?\s*oliva\s+i\s+want\s+to\s+know\s+more\s+about\s+services\s+in\s+[a-z\s]+,\s*[a-z\s]+\s+clinic$",
            r"^hi,?\s*oliva\s+i\s+want\s+to\s+know\s+more\s+about\s+your\s+services$",
        ]
        prefill_detected = any(re.match(rx, normalized_body, flags=re.IGNORECASE) for rx in prefill_regexes)
        if prefill_detected:
            try:
                token_entry_prefill = get_latest_token(db)
                try:
                    incoming_phone_id = (value or {}).get("metadata", {}).get("phone_number_id")
                except Exception:
                    incoming_phone_id = None
                if token_entry_prefill and token_entry_prefill.token:
                    access_token_prefill = token_entry_prefill.token
                    phone_id_prefill = incoming_phone_id or os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                    lang_code_prefill = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                    body_components_prefill = [{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": (sender_name or wa_id or "there")}
                        ],
                    }]
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template_attempt",
                            "message": "Sending mr_welcome_temp...",
                            "params": {"body_param_1": (sender_name or wa_id or "there"), "lang": lang_code_prefill, "phone_id": phone_id_prefill},
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass

                    # Local import to avoid circulars
                    from controllers.auto_welcome_controller import _send_template

                    resp_prefill = _send_template(
                        wa_id=wa_id,
                        template_name="mr_welcome_temp",
                        access_token=access_token_prefill,
                        phone_id=phone_id_prefill,
                        components=body_components_prefill,
                        lang_code=lang_code_prefill,
                    )
                    if resp_prefill.status_code == 200:
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template",
                                "message": "mr_welcome_temp sent",
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                        handled_text = True
                        return {"status": "welcome_sent", "message_id": message_id}
                    else:
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template_error",
                                "message": "mr_welcome_temp failed",
                                "status_code": resp_prefill.status_code,
                                "error": (resp_prefill.text[:500] if isinstance(resp_prefill.text, str) else str(resp_prefill.text)),
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                        handled_text = True
                        return {"status": "welcome_failed", "message_id": message_id}
                else:
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template_error",
                            "message": "mr_welcome_temp not sent: no WhatsApp token",
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
            except Exception:
                # Continue to other logic below even if welcome attempt fails
                pass

        # 4) Contact verification heuristics
        has_phone = re.search(r"\b\d{10}\b", normalized_body) or re.search(r"\+91", normalized_body)
        has_name_keywords = any(keyword in normalized_body for keyword in ["name", "i am", "my name", "call me"])
        digit_count = len(re.findall(r"\d", normalized_body))
        name_token_count = len(re.findall(r"[A-Za-z][A-Za-z\-']+", body_text))
        has_any_name_token = name_token_count >= 1
        should_verify = bool(has_phone or has_name_keywords or (has_any_name_token and digit_count >= 7))

        if should_verify:
            # Local import to avoid circulars
            from controllers.auto_welcome_controller import _verify_contact_with_openai, _send_template

            verification = _verify_contact_with_openai(body_text)
            try:
                await manager.broadcast({
                    "from": to_wa_id,
                    "to": wa_id,
                    "type": "contact_verification",
                    "result": verification,
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception:
                pass

            try:
                if verification.get("valid"):
                    await send_message_to_waid(
                        wa_id,
                        f"✅ Received details. Name: {verification.get('name')} | Phone: {verification.get('phone')}",
                        db,
                    )

                    # Try sending mr_treatment template; fallback to interactive buttons if it fails
                    try:
                        token_entry_btn = get_latest_token(db)
                        if token_entry_btn and token_entry_btn.token:
                            access_token_btn = token_entry_btn.token
                            phone_id_btn = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                            lang_code_btn = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                            resp_btn = _send_template(
                                wa_id=wa_id,
                                template_name="mr_treatment",
                                access_token=access_token_btn,
                                phone_id=phone_id_btn,
                                components=None,
                                lang_code=lang_code_btn,
                            )
                            if resp_btn.status_code == 200:
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template",
                                        "message": "mr_treatment sent",
                                        "timestamp": datetime.now().isoformat(),
                                    })
                                except Exception:
                                    pass
                            else:
                                # Fallback to interactive buttons
                                headers_btn = {
                                    "Authorization": f"Bearer {access_token_btn}",
                                    "Content-Type": "application/json",
                                }
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
                                                {"type": "reply", "reply": {"id": "body", "title": "Body"}},
                                            ]
                                        },
                                    },
                                }
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template_error",
                                        "message": "mr_treatment failed",
                                        "status_code": resp_btn.status_code,
                                        "error": (resp_btn.text[:500] if isinstance(resp_btn.text, str) else str(resp_btn.text)),
                                        "timestamp": datetime.now().isoformat(),
                                    })
                                except Exception:
                                    pass
                                requests.post(get_messages_url(phone_id_btn), headers=headers_btn, json=payload_btn)
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "interactive",
                                        "message": "Please choose your area of concern:",
                                        "timestamp": datetime.now().isoformat(),
                                        "meta": {"kind": "buttons", "options": ["Skin", "Hair", "Body"]},
                                    })
                                except Exception:
                                    pass
                    except Exception:
                        pass
                else:
                    issues: list[str] = []
                    name_val = (verification.get("name") or "").strip() if isinstance(verification.get("name"), str) else None
                    phone_val = (verification.get("phone") or "").strip() if isinstance(verification.get("phone"), str) else None

                    # Name validation: at least 2 words
                    if not name_val:
                        issues.append("- Name missing")
                    else:
                        name_tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", name_val)
                        if len(name_tokens) < 2:
                            issues.append("- Name should have at least 2 words")

                    # Phone validation: +91XXXXXXXXXX or 10 digits
                    if not phone_val:
                        issues.append("- Phone number missing")
                    else:
                        digits = re.sub(r"\D", "", phone_val)
                        if digits.startswith("91") and len(digits) == 12:
                            digits = digits[2:]
                        if len(digits) != 10:
                            issues.append("- Phone must be 10 digits (Indian mobile)")

                    corrective = (
                        "❌ I couldn't verify your details.\n"
                        + (("\n".join(issues) + "\n") if issues else "")
                        + "\nPlease reply with your full name and a 10-digit mobile number in one message.\n"
                          "Example: Rahul Sharma 9876543210"
                    )
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "contact_verification_failed",
                            "issues": issues,
                            "verification": verification,
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "contact_verification_corrective_attempt",
                            "message": corrective,
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass

                    # Try sending via utility first
                    try:
                        await send_message_to_waid(wa_id, corrective, db)
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "contact_verification_corrective_sent",
                                "via": "utility",
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                    except Exception:
                        # Fallback: send directly via WhatsApp API
                        try:
                            token_entry_fb = get_latest_token(db)
                            if token_entry_fb and token_entry_fb.token:
                                access_token_fb = token_entry_fb.token
                                try:
                                    incoming_phone_id_fb = (value or {}).get("metadata", {}).get("phone_number_id")
                                except Exception:
                                    incoming_phone_id_fb = None
                                phone_id_fb = incoming_phone_id_fb or os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                                headers_fb = {"Authorization": f"Bearer {access_token_fb}", "Content-Type": "application/json"}
                                payload_fb = {
                                    "messaging_product": "whatsapp",
                                    "to": wa_id,
                                    "type": "text",
                                    "text": {"body": corrective},
                                }
                                resp_fb = requests.post(get_messages_url(phone_id_fb), headers=headers_fb, json=payload_fb)
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "contact_verification_corrective_sent",
                                        "via": "fallback",
                                        "status_code": resp_fb.status_code,
                                        "timestamp": datetime.now().isoformat(),
                                    })
                                except Exception:
                                    pass
                            else:
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "contact_verification_corrective_failed",
                                        "reason": "no_token",
                                        "timestamp": datetime.now().isoformat(),
                                    })
                                except Exception:
                                    pass
                        except Exception as fb_err:
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "contact_verification_corrective_failed",
                                    "reason": str(fb_err)[:200],
                                    "timestamp": datetime.now().isoformat(),
                                })
                            except Exception:
                                pass
            except Exception as e:
                # Non-fatal; continue webhook
                print(f"[treament_flow] Error in validation flow: {e}")
            handled_text = True

    return {"status": "skipped" if not handled_text else "handled", "message_id": message_id}


async def run_treatment_buttons_flow(
    db: Session,
    *,
    wa_id: str,
    to_wa_id: str,
    message_id: str,
    btn_id: str | None = None,
    btn_text: str | None = None,
    btn_payload: str | None = None,
) -> Dict[str, Any]:
    """Handle Skin/Hair/Body treatment topic buttons and list selections.

    Mirrors the behavior previously inline in the webhook controller.
    Returns a status dict and performs necessary broadcasts.
    """

    # Topic buttons: Skin / Hair / Body
    topic = (btn_id or btn_text or "").strip().lower()
    if topic in {"skin", "hair", "body"}:
        try:
            token_entry2 = get_latest_token(db)
            if token_entry2 and token_entry2.token:
                access_token2 = token_entry2.token
                phone_id2 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                from controllers.auto_welcome_controller import _send_template
                lang_code = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                if topic == "skin":
                    resp_skin = _send_template(wa_id=wa_id, template_name="skin_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_skin.status_code == 200 else "template_error",
                            "message": "skin_treat_flow sent" if resp_skin.status_code == 200 else "skin_treat_flow failed",
                            **({"status_code": resp_skin.status_code} if resp_skin.status_code != 200 else {}),
                        })
                    except Exception:
                        pass

                    headers2 = {"Authorization": f"Bearer {access_token2}", "Content-Type": "application/json"}
                    payload_list = {
                        "messaging_product": "whatsapp",
                        "to": wa_id,
                        "type": "interactive",
                        "interactive": {
                            "type": "list",
                            "body": {"text": "Please select your Skin concern:"},
                            "action": {
                                "button": "Select Concern",
                                "sections": [
                                    {
                                        "title": "Skin Concerns",
                                        "rows": [
                                            {"id": "acne", "title": "Acne / Acne Scars"},
                                            {"id": "pigmentation", "title": "Pigmentation & Uneven Skin Tone"},
                                            {"id": "antiaging", "title": "Anti-Aging & Skin Rejuvenation"},
                                            {"id": "laser", "title": "Laser Hair Removal"},
                                            {"id": "other_skin", "title": "Other Skin Concerns"},
                                        ],
                                    }
                                ],
                            },
                        },
                    }
                    requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                    return {"status": "list_sent", "message_id": message_id}

                if topic == "hair":
                    resp_hair = _send_template(wa_id=wa_id, template_name="hair_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_hair.status_code == 200 else "template_error",
                            "message": "hair_treat_flow sent" if resp_hair.status_code == 200 else "hair_treat_flow failed",
                            **({"status_code": resp_hair.status_code} if resp_hair.status_code != 200 else {}),
                        })
                    except Exception:
                        pass
                    return {"status": "hair_template_sent", "message_id": message_id}

                if topic == "body":
                    resp_body = _send_template(wa_id=wa_id, template_name="body_treat_flow", access_token=access_token2, phone_id=phone_id2, components=None, lang_code=lang_code)
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_body.status_code == 200 else "template_error",
                            "message": "body_treat_flow sent" if resp_body.status_code == 200 else "body_treat_flow failed",
                            **({"status_code": resp_body.status_code} if resp_body.status_code != 200 else {}),
                        })
                    except Exception:
                        pass
                    return {"status": "body_template_sent", "message_id": message_id}
        except Exception:
            pass

    # List selections arriving as plain buttons
    norm_btn = (btn_id or btn_text or btn_payload or "").strip().lower()
    skin_concerns = {
        "acne / acne scars",
        "pigmentation",
        "uneven skin tone",
        "anti-aging ",
        "skin rejuvenation",
        "laser hair removal",
        "other skin concerns",
    }
    hair_concerns = {
        "hair loss / hair fall",
        "hair transplant",
        "dandruff & scalp care",
        "other hair concerns",
    }
    body_concerns = {
        "weight management",
        "body contouring",
        "weight loss",
        "other body concerns",
    }

    if norm_btn in skin_concerns or norm_btn in hair_concerns or norm_btn in body_concerns:
        try:
            token_entry_book = get_latest_token(db)
            if token_entry_book and token_entry_book.token:
                phone_id_book = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                lang_code_book = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                from controllers.auto_welcome_controller import _send_template
                resp_book = _send_template(
                    wa_id=wa_id,
                    template_name="booking_appoint",
                    access_token=token_entry_book.token,
                    phone_id=phone_id_book,
                    components=None,
                    lang_code=lang_code_book,
                )
                try:
                    await manager.broadcast({
                        "from": to_wa_id,
                        "to": wa_id,
                        "type": "template" if resp_book.status_code == 200 else "template_error",
                        "message": "booking_appoint sent" if resp_book.status_code == 200 else "booking_appoint failed",
                        **({"status_code": resp_book.status_code} if resp_book.status_code != 200 else {}),
                    })
                except Exception:
                    pass
        except Exception:
            pass

        try:
            token_entry3 = get_latest_token(db)
            if token_entry3 and token_entry3.token:
                access_token3 = token_entry3.token
                headers3 = {"Authorization": f"Bearer {access_token3}", "Content-Type": "application/json"}
                phone_id3 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                payload_buttons = {
                    "messaging_product": "whatsapp",
                    "to": wa_id,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {"text": "Please choose one option:"},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 Book an Appointment"}},
                                {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde Request a Call Back"}},
                            ]
                        },
                    },
                }
                requests.post(get_messages_url(phone_id3), headers=headers3, json=payload_buttons)
                return {"status": "next_actions_sent", "message_id": message_id}
        except Exception:
            pass

    return {"status": "skipped"}


async def run_book_appointment_flow(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Trigger the appointment date list for a user.

    Delegates to the existing date list sender while avoiding circular imports.
    """

    try:
        # Local import to avoid circular dependency
        from controllers.web_socket import send_date_list  # type: ignore
        await send_date_list(wa_id, db)
        return {"status": "date_list_sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def run_confirm_appointment_flow(
    db: Session,
    *,
    wa_id: str,
    date_iso: str,
    time_label: str,
) -> Dict[str, Any]:
    """Confirm an appointment for the provided date and time.

    Delegates to the existing confirm helper to send confirmation and follow-ups.
    """

    try:
        # Local import to avoid circular dependency
        from controllers.web_socket import _confirm_appointment  # type: ignore
        await _confirm_appointment(wa_id, db, date_iso, time_label)
        return {"status": "appointment_captured", "date": date_iso, "time": time_label}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}

