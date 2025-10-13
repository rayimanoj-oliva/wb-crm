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

    # 1) Do NOT persist/broadcast inbound text here to avoid duplicates.
    #    The main webhook controller handles saving + broadcasting once.
    #    Continue with flow analysis only.
    if message_type == "text":
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
                    # Broadcast result to ChatWindow
                    try:
                        await manager.broadcast({
                            "from": to_wa_id,
                            "to": wa_id,
                            "type": "template" if resp_prefill.status_code == 200 else "template_error",
                            "message": "mr_welcome_temp sent" if resp_prefill.status_code == 200 else "mr_welcome_temp failed",
                            **({"status_code": resp_prefill.status_code} if resp_prefill.status_code != 200 else {}),
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
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

                        # Immediately proceed to treatment flow without asking name/phone
                        try:
                            components_treat = None
                            resp_treat = _send_template(
                                wa_id=wa_id,
                                template_name="mr_treatment",
                                access_token=access_token_prefill,
                                phone_id=phone_id_prefill,
                                components=components_treat,
                                lang_code=lang_code_prefill,
                            )
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template" if resp_treat.status_code == 200 else "template_error",
                                    "message": "mr_treatment sent" if resp_treat.status_code == 200 else "mr_treatment failed",
                                    **({"status_code": resp_treat.status_code} if resp_treat.status_code != 200 else {}),
                                    "timestamp": datetime.now().isoformat(),
                                })
                            except Exception:
                                pass
                            if resp_treat.status_code != 200:
                                # Fallback to interactive buttons (Skin/Hair/Body)
                                headers_btn2 = {
                                    "Authorization": f"Bearer {access_token_prefill}",
                                    "Content-Type": "application/json",
                                }
                                payload_btn2 = {
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
                                requests.post(get_messages_url(phone_id_prefill), headers=headers_btn2, json=payload_btn2)
                        except Exception:
                            pass

                        handled_text = True
                        return {"status": "welcome_and_treatment_sent", "message_id": message_id}
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

            # Fallback: if model/regex marked invalid, try strict local extraction but only accept plausible names
            if not bool(verification.get("valid")):
                try:
                    # Normalize phone to +91XXXXXXXXXX
                    def _norm_phone(p: str | None) -> str | None:
                        if not isinstance(p, str):
                            return None
                        digits = re.sub(r"\D", "", p)
                        if len(digits) < 10:
                            return None
                        last10 = digits[-10:]
                        if len(last10) != 10:
                            return None
                        return "+91" + last10

                    # Extract phone from message text
                    phone_match = re.search(r"\+91[-\s]?(\d{10})", body_text) or re.search(r"\b(\d{10})\b", body_text)
                    fallback_phone = _norm_phone(phone_match.group(1) if phone_match else None)

                    # Extract a plausible name: enforce vowels, consonants, token structure
                    name_tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", body_text)
                    fallback_name = " ".join(name_tokens[:3]) if name_tokens else None
                    letters_only = re.sub(r"[^A-Za-z]", "", fallback_name or "")
                    has_min = len(letters_only) >= 3
                    has_vowel = re.search(r"[AEIOUaeiou]", letters_only) is not None
                    has_consonant = re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only) is not None
                    long_consonant_cluster = re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]{5,}", letters_only) is not None
                    tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", fallback_name or "")
                    token_ok = (len(tokens) >= 2 and all(len(re.sub(r"[^A-Za-z]", "", t)) >= 2 for t in tokens[:2])) or (len(tokens) == 1 and len(letters_only) >= 4)
                    blacklist = {"asd", "sdf", "dfg", "qwe", "zxc", "sdfhj", "qwert", "qwerty", "abc"}
                    is_blacklisted = (fallback_name or "").strip().lower() in blacklist
                    is_name_ok = has_min and has_vowel and has_consonant and token_ok and not long_consonant_cluster and not is_blacklisted

                    if fallback_phone and is_name_ok:
                        verification = {
                            "valid": True,
                            "name": fallback_name,
                            "phone": fallback_phone,
                            "reason": "local fallback accepted"
                        }
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "contact_verification_fallback",
                                "result": verification,
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                if verification.get("valid"):
                    await send_message_to_waid(
                        wa_id,
                        f"✅ Received details. Name: {verification.get('name')} | Phone: {verification.get('phone')}",
                        db,
                    )
                    try:
                        # If user has selected a date/time already, include it in the thank-you
                        date_label = None
                        time_label = None
                        try:
                            from controllers.web_socket import appointment_state  # type: ignore
                            appt = appointment_state.get(wa_id) or {}
                            date_label = appt.get("date")
                            time_label = appt.get("time")
                        except Exception:
                            pass

                        if date_label and time_label:
                            msg = (
                                f"✅ Thank you! We've recorded your details: {verification.get('name')} ({verification.get('phone')}). "
                                f"Your preferred appointment is on {date_label} at {time_label}. Your appointment is booked, and our team will call to confirm shortly."
                            )
                        else:
                            msg = (
                                f"✅ Thank you! We've recorded your details: {verification.get('name')} ({verification.get('phone')}). Our team will contact you shortly to assist further."
                            )
                        await send_message_to_waid(wa_id, msg, db)
                    except Exception:
                        pass

                    # Do not trigger treatment template here anymore
                    handled_text = True
                    return {"status": "contact_captured", "message_id": message_id}
                else:
                    issues: list[str] = []
                    name_val = (verification.get("name") or "").strip() if isinstance(verification.get("name"), str) else None
                    phone_val = (verification.get("phone") or "").strip() if isinstance(verification.get("phone"), str) else None

                    # Name validation: at least 3 letters AND plausible human pattern (vowel+consonant, not gibberish)
                    if not name_val:
                        issues.append("- Name missing")
                    else:
                        letters_only = re.sub(r"[^A-Za-z]", "", name_val)
                        has_min = len(letters_only) >= 3
                        has_vowel = re.search(r"[AEIOUaeiou]", letters_only) is not None
                        has_consonant = re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only) is not None
                        long_consonant_cluster = re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]{5,}", letters_only) is not None
                        tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", name_val)
                        token_ok = (len(tokens) >= 2 and all(len(re.sub(r"[^A-Za-z]", "", t)) >= 2 for t in tokens[:2])) or (len(tokens) == 1 and len(letters_only) >= 4)
                        blacklist = {"asd", "sdf", "dfg", "qwe", "zxc", "sdfhj", "qwert", "qwerty", "abc"}
                        is_blacklisted = name_val.strip().lower() in blacklist
                        if not (has_min and has_vowel and has_consonant and token_ok) or long_consonant_cluster or is_blacklisted:
                            issues.append("- Name must have at least 3 letters")

                    # Phone validation: +91XXXXXXXXXX or 10 digits
                    if not phone_val:
                        issues.append("- Phone number missing")
                    else:
                        digits = re.sub(r"\D", "", phone_val)
                        if digits.startswith("91") and len(digits) == 12:
                            digits = digits[2:]
                        if len(digits) != 10:
                            issues.append("- Phone must be 10 digits (Indian mobile)")

                    # Skip corrective messaging here to avoid asking for full name + phone together.
                    # Let the main websocket flow handle name/phone correction interactively.
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
                    return {"status": "contact_verification_invalid", "message_id": message_id, "issues": issues}
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


async def run_appointment_buttons_flow(
    db: Session,
    *,
    wa_id: str,
    btn_id: str | None = None,
    btn_text: str | None = None,
    btn_payload: str | None = None,
) -> Dict[str, Any]:
    """Handle appointment related buttons: book_appointment, request_callback, and time_* selections.

    Uses existing helpers in the websocket controller for date list and time confirmation.
    """

    try:
        normalized_id = (btn_id or "").strip().lower()
        normalized_text = (btn_text or "").strip().lower()
        normalized_payload = (btn_payload or "").strip().lower()

        # Book appointment
        if (
            normalized_id == "book_appointment"
            or normalized_text in {"book an appointment", "book appointment"}
            or normalized_payload in {"book an appointment", "book appointment"}
        ):
            try:
                from controllers.web_socket import send_date_list  # type: ignore
                await send_date_list(wa_id, db)
                return {"status": "date_list_sent"}
            except Exception as e:
                return {"status": "failed", "error": str(e)[:200]}

        # Request a call back
        if (
            normalized_id == "request_callback"
            or normalized_text == "request a call back"
            or normalized_payload == "request a call back"
        ):
            try:
                await send_message_to_waid(
                    wa_id,
                    "📌 Thank you for your interest! One of our team members will contact you shortly to assist further.",
                    db,
                )
            except Exception:
                pass
            return {"status": "callback_ack"}

        # Time selection
        time_map = {
            "time_10_00": "10:00 AM",
            "time_14_00": "2:00 PM",
            "time_18_00": "6:00 PM",
        }
        possible_time = (
            time_map.get(normalized_id)
            or (btn_text or "").strip()
            or (btn_payload or "").strip()
        )
        if (
            normalized_id.startswith("time_")
            or possible_time in ["10:00 AM", "2:00 PM", "6:00 PM"]
        ):
            try:
                from controllers.web_socket import appointment_state, send_date_list  # type: ignore
                time_label = time_map.get(normalized_id) or (btn_text or btn_payload or "").strip()
                date_iso = (appointment_state.get(wa_id) or {}).get("date")
                if date_iso and time_label:
                    result = await run_confirm_appointment_flow(
                        db,
                        wa_id=wa_id,
                        date_iso=date_iso,
                        time_label=time_label,
                    )
                    if result.get("status") == "appointment_captured":
                        return result
                # Need date first
                await send_message_to_waid(wa_id, "Please select a date first.", db)
                await send_date_list(wa_id, db)
                return {"status": "need_date_first"}
            except Exception as e:
                return {"status": "failed", "error": str(e)[:200]}

    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}

    return {"status": "skipped"}