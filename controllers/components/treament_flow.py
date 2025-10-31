from __future__ import annotations

from datetime import datetime
from typing import Optional, Any, Dict

import os
import re
import requests

from sqlalchemy.orm import Session

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

        # 3) Prefill detection for mr_welcome
        prefill_regexes = [
            r"^hi,?\s*oliva\s+i\s+want\s+to\s+know\s+more\s+about\s+services\s+in\s+[a-z\s]+,\s*[a-z\s]+\s+clinic$",
            r"^hi,?\s*oliva\s+i\s+want\s+to\s+know\s+more\s+about\s+your\s+services$",
        ]
        prefill_detected = any(re.match(rx, normalized_body, flags=re.IGNORECASE) for rx in prefill_regexes)
        if prefill_detected:
            try:
                # Extract location and city from the incoming prefill text if present
                # Expected: "hi oliva i want to know more about services in <location>, <city> clinic"
                extracted_location = None
                extracted_city = None
                try:
                    _m = re.search(r"services\s+in\s+([a-z\s]+),\s*([a-z\s]+)\s+clinic$", normalized_body, flags=re.IGNORECASE)
                    if _m:
                        extracted_location = (_m.group(1) or "").strip().title()
                        extracted_city = (_m.group(2) or "").strip().title()
                except Exception:
                    pass

                # Persist into state for later lead creation
                try:
                    from controllers.web_socket import appointment_state, lead_appointment_state  # type: ignore
                    st_prefill = appointment_state.get(wa_id) or {}
                    if extracted_city:
                        st_prefill["selected_city"] = extracted_city
                    if extracted_location:
                        st_prefill["selected_location"] = extracted_location
                    appointment_state[wa_id] = st_prefill
                    # Mirror minimal info into lead_appointment_state
                    try:
                        lst_prefill = lead_appointment_state.get(wa_id) or {}
                        if extracted_city:
                            lst_prefill["selected_city"] = extracted_city
                        if extracted_location:
                            lst_prefill["selected_location"] = extracted_location
                        lead_appointment_state[wa_id] = lst_prefill
                    except Exception:
                        pass
                except Exception:
                    pass

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
                            "message": "Sending mr_welcome...",
                            "params": {"body_param_1": (sender_name or wa_id or "there"), "lang": lang_code_prefill, "phone_id": phone_id_prefill},
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass

                    # Local import to avoid circulars
                    from controllers.auto_welcome_controller import _send_template

                    resp_prefill = _send_template(
                        wa_id=wa_id,
                        template_name="mr_welcome",
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
                            "message": "mr_welcome sent" if resp_prefill.status_code == 200 else "mr_welcome failed",
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
                                "message": "mr_welcome sent",
                                "timestamp": datetime.now().isoformat(),
                            })
                        except Exception:
                            pass
                        # Schedule follow-up only for mr_welcome
                        try:
                            from services.followup_service import schedule_next_followup as _schedule
                            from services.customer_service import get_customer_record_by_wa_id as _get_c
                            _cust = _get_c(db, wa_id)
                            if _cust:
                                _schedule(db, customer_id=_cust.id, delay_minutes=2, stage_label="mr_welcome_sent")
                        except Exception:
                            pass

                        # Do NOT send mr_treatment here; it will be sent after city selection

                        # Mark context and set treatment flag
                        try:
                            from controllers.web_socket import appointment_state  # type: ignore
                            st = appointment_state.get(wa_id) or {}
                            st["flow_context"] = "treatment"
                            st["from_treatment_flow"] = True
                            appointment_state[wa_id] = st
                        except Exception:
                            pass

                        # Build and send name/phone confirmation with Yes/No
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
                            await send_message_to_waid(wa_id, confirm_msg, db)

                            token_entry = get_latest_token(db)
                            if token_entry and token_entry.token:
                                access_token = token_entry.token
                                phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                                headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
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
                                requests.post(get_messages_url(phone_id), headers=headers, json=payload_btn)
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Could not send confirmation: {e}")

                        handled_text = True
                        return {"status": "awaiting_confirmation", "message_id": message_id}
                    else:
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "template_error",
                                "message": "mr_welcome failed",
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
                            "message": "mr_welcome not sent: no WhatsApp token",
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        pass
            except Exception:
                # Continue to other logic below even if welcome attempt fails
                pass

        # Name/Contact verification removed as per new requirements.

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
    """Handle Skin/Hair/Body treatment topic buttons and list selections."""
    # Strongest possible check: don't process any treatment action if this is a catalog/buy flow.
    catalog_triggers = {"buy_products", "buy product", "buy products", "show catalogue", "catalogue", "catalog", "browse products"}
    for val in (btn_id, btn_text, btn_payload):
        if val and any(kw in val.lower() for kw in catalog_triggers):
            print(f"[treatment_flow] DEBUG - Skipping treatment logic for catalog trigger: {val}")
            return {"status": "skipped"}

    # Topic buttons: Skin / Hair / Body
    topic = (btn_id or btn_text or "").strip().lower()
    if topic in {"skin", "hair", "body"}:
        # NOTE: Do NOT set any fallback concern here.
        # We should only persist the precise list selection the user makes next.
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
                                            {"id": "dandruff", "title": "Dandruff & Scalp Care"},
                                            {"id": "other_skin", "title": "Other Skin Concerns"},
                                        ],
                                    }
                                ],
                            },
                        },
                    }
                    resp_list = requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                    if resp_list.status_code == 200:
                        try:
                            # Save outbound message to database
                            response_data = resp_list.json()
                            message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                            
                            from services.message_service import create_message
                            from schemas.message_schema import MessageCreate
                            
                            outbound_message = MessageCreate(
                                message_id=message_id,
                                from_wa_id=to_wa_id,
                                to_wa_id=wa_id,
                                type="interactive",
                                body=f"Choose your {topic} treatment:",
                                timestamp=datetime.now(),
                                customer_id=customer.id,
                            )
                            create_message(db, outbound_message)
                            print(f"[treatment_flow] DEBUG - Outbound treatment list saved to database: {message_id}")
                            
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "interactive",
                                "message": f"Choose your {topic} treatment:",
                                "timestamp": datetime.now().isoformat(),
                                "meta": {"kind": "list", "section": f"{topic.title()} Treatments"}
                            })
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
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
    # Canonicalize label/id to avoid hyphen/space/ampersand differences
    def _canon(txt: str) -> str:
        try:
            import re as _re
            return _re.sub(r"[^a-z0-9]+", " ", (txt or "").lower()).strip()
        except Exception:
            return (txt or "").lower().strip()

    canon_btn = _canon(norm_btn)

    skin_concerns = {
        "acne acne scars",
        "pigmentation",
        "uneven skin tone",
        "anti aging",
        "skin rejuvenation",
        "laser hair removal",
        "other skin concerns",
    }
    hair_concerns = {
        "hair loss hair fall",
        "hair transplant",
        "dandruff scalp care",
        "other hair concerns",
    }
    body_concerns = {
        "weight management",
        "body contouring",
        "weight loss",
        "other body concerns",
    }

    if canon_btn in skin_concerns or canon_btn in hair_concerns or canon_btn in body_concerns:
        # Persist the user's selected concern so lead creation can map it later
        try:
            # Map canonical keys to display labels used in DB mappings
            synonyms_to_canonical = {
                # Skin
                "acne acne scars": "Acne / Acne Scars",
                "pigmentation": "Pigmentation & Uneven Skin Tone",
                "uneven skin tone": "Pigmentation & Uneven Skin Tone",
                "anti aging": "Anti-Aging & Skin Rejuvenation",
                "skin rejuvenation": "Anti-Aging & Skin Rejuvenation",
                "laser hair removal": "Laser Hair Removal",
                "other skin concerns": "Other Skin Concerns",
                # Hair
                "hair loss hair fall": "Hair Loss / Hair Fall",
                "hair transplant": "Hair Transplant",
                "dandruff scalp care": "Dandruff & Scalp Care",
                "other hair concerns": "Other Hair Concerns",
                # Body
                "weight management": "Weight Management",
                "body contouring": "Body Contouring",
                "weight loss": "Weight Loss",
                "other body concerns": "Other Body Concerns",
            }

            selected_concern_label = synonyms_to_canonical.get(canon_btn, (btn_text or btn_payload or btn_id or "").strip())

            # Save to in-memory state used across flows
            from controllers.web_socket import appointment_state, lead_appointment_state  # type: ignore
            try:
                if wa_id not in appointment_state:
                    appointment_state[wa_id] = {}
                appointment_state[wa_id]["selected_concern"] = selected_concern_label
            except Exception:
                pass
            try:
                if wa_id not in lead_appointment_state:
                    lead_appointment_state[wa_id] = {}
                lead_appointment_state[wa_id]["selected_concern"] = selected_concern_label
            except Exception:
                pass
        except Exception:
            pass
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
                        "body": {"text": "Please choose one of the following options:"},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 📅 Book an Appointment"}},
                                {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde 📞 Request a Call Back"}},
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
        from controllers.components.interactive_type import send_week_list  # type: ignore
        await send_week_list(db, wa_id)
        return {"status": "week_list_sent"}
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
                # If in treatment context, create lead immediately and send thank you
                from controllers.web_socket import appointment_state  # type: ignore
                st = appointment_state.get(wa_id) or {}
                flow_ctx = st.get("flow_context")
                if flow_ctx == "treatment":
                    try:
                        from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
                        from services.customer_service import get_customer_record_by_wa_id
                        customer = get_customer_record_by_wa_id(db, wa_id)
                        selected_concern = (st or {}).get("selected_concern")
                        appointment_details = {
                            "flow_type": "treatment_flow",
                            "treatment_selected": True,
                            "no_scheduling_required": True,
                            "selected_concern": selected_concern,
                        }
                        await create_lead_for_appointment(
                            db=db,
                            wa_id=wa_id,
                            customer=customer,
                            appointment_details=appointment_details,
                            lead_status="PENDING",
                            appointment_preference="Treatment consultation - no specific appointment time requested",
                        )
                    except Exception:
                        pass
                    # Thank you message
                    await send_message_to_waid(
                        wa_id,
                        "✅ Thank you! Our team will call and confirm your appointment shortly.",
                        db,
                    )
                    # Stop any follow-ups for completed flow
                    try:
                        from services.followup_service import mark_customer_replied as _mark_replied
                        from services.customer_service import get_customer_record_by_wa_id as _get_cust
                        _cust = _get_cust(db, wa_id)
                        if _cust:
                            _mark_replied(db, customer_id=_cust.id)
                    except Exception:
                        pass
                    # Clear state
                    try:
                        if wa_id in appointment_state:
                            appointment_state.pop(wa_id, None)
                    except Exception:
                        pass
                    return {"status": "treatment_lead_created"}
                else:
                    # Non-treatment flows: route to city selection
                    st["flow_context"] = "treatment"
                    appointment_state[wa_id] = st
                    from controllers.components.lead_appointment_flow.city_selection import send_city_selection
                    result = await send_city_selection(db, wa_id=wa_id)
                    return {"status": "city_list_sent", "result": result}
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
                # Stop any follow-ups for completed flow
                try:
                    from services.followup_service import mark_customer_replied as _mark_replied
                    from services.customer_service import get_customer_record_by_wa_id as _get_cust
                    _cust = _get_cust(db, wa_id)
                    if _cust:
                        _mark_replied(db, customer_id=_cust.id)
                except Exception:
                    pass
                
                # Create lead in Zoho for callback request
                try:
                    from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment
                    from services.customer_service import get_customer_record_by_wa_id
                    customer = get_customer_record_by_wa_id(db, wa_id)
                    
                    # Prepare appointment details for callback request
                    appointment_details = {
                        "flow_type": "treatment_flow",
                        "treatment_selected": True,
                        "callback_requested": True,
                        "no_scheduling_required": True
                    }
                    
                    lead_result = await create_lead_for_appointment(
                        db=db,
                        wa_id=wa_id,
                        customer=customer,
                        appointment_details=appointment_details,
                        lead_status="PENDING",
                        appointment_preference="Treatment consultation - callback requested"
                    )
                    print(f"[treatment_flow] DEBUG - Lead creation result (callback): {lead_result}")
                except Exception as e:
                    print(f"[treatment_flow] WARNING - Could not create lead (callback): {e}")
                    
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
                # Need date first -> start from week selection
                await send_message_to_waid(wa_id, "Please select a week and then a date.", db)
                # Use TREATMENT FLOW specific week list (original function)
                from controllers.components.interactive_type import send_week_list  # type: ignore
                await send_week_list(db, wa_id)
                return {"status": "need_date_first"}
            except Exception as e:
                return {"status": "failed", "error": str(e)[:200]}

    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}

    return {"status": "skipped"}