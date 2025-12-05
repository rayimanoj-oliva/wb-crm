from datetime import datetime
from fastapi import HTTPException


import requests

from schemas.customer_schema import CustomerCreate
from sqlalchemy.orm import Session
from models.models import Category, SubCategory, Product
from config.constants import get_messages_url
import os
from schemas.message_schema import MessageCreate
from services import whatsapp_service, customer_service, message_service
from services.followup_service import schedule_next_followup
from utils.ws_manager import manager
from marketing.whatsapp_numbers import WHATSAPP_NUMBERS

def _resolve_credentials(db, *, hint_phone_id: str | None = None, hint_display_number: str | None = None, wa_id: str | None = None):
    """Pick the correct token and phone_id for outbound sends.

    CRITICAL: For treatment flow, ALWAYS use incoming_phone_id (the number customer messaged to).
    This ensures replies go from the same number customer contacted, preventing confusion.
    
    Preference order:
    1) Stored incoming_phone_id from state (MOST IMPORTANT - the number customer messaged to)
    2) Explicit hint_phone_id mapping (if incoming_phone_id not set)
    3) Stored treatment_flow_phone_id from state (if incoming_phone_id not set)
    4) Stored lead_appointment_phone_id from lead state (if incoming_phone_id not set)
    5) Env WHATSAPP_PHONE_ID mapping
    6) Single entry in WHATSAPP_NUMBERS
    7) Fallback to DB token + env WHATSAPP_PHONE_ID
    """
    # CRITICAL: Check stored incoming_phone_id FIRST (the number customer messaged to)
    # This is the MOST important - ensures replies go from the same number customer contacted
    # DO NOT fallback to other numbers if incoming_phone_id is set - this prevents confusion
    if wa_id:
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            
            # FIRST: Check incoming_phone_id - this is the number customer messaged to
            incoming_phone_id = st.get("incoming_phone_id")
            if incoming_phone_id and isinstance(WHATSAPP_NUMBERS, dict) and incoming_phone_id in WHATSAPP_NUMBERS:
                cfg = WHATSAPP_NUMBERS.get(incoming_phone_id) or {}
                tok = cfg.get("token")
                if tok:
                    print(f"[_resolve_credentials] RESOLVED via incoming_phone_id: {incoming_phone_id} for wa_id={wa_id}")
                    return tok, incoming_phone_id
                else:
                    print(f"[_resolve_credentials] WARNING - incoming_phone_id {incoming_phone_id} found but no token available for wa_id={wa_id}")
        except Exception as e:
            print(f"[_resolve_credentials] WARNING - Could not check incoming_phone_id: {e}")

    # 2) Explicit phone_id hint (only if incoming_phone_id not set)
    if hint_phone_id and isinstance(WHATSAPP_NUMBERS, dict) and hint_phone_id in WHATSAPP_NUMBERS:
        cfg = WHATSAPP_NUMBERS.get(hint_phone_id) or {}
        tok = cfg.get("token")
        if tok:
            print(f"[_resolve_credentials] RESOLVED via hint_phone_id: {hint_phone_id} for wa_id={wa_id}")
            return tok, hint_phone_id

    # 3) Check for treatment flow phone_id (only if incoming_phone_id not set)
    if wa_id:
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            
            stored_phone_id = st.get("treatment_flow_phone_id")
            if stored_phone_id and isinstance(WHATSAPP_NUMBERS, dict) and stored_phone_id in WHATSAPP_NUMBERS:
                cfg = WHATSAPP_NUMBERS.get(stored_phone_id) or {}
                tok = cfg.get("token")
                if tok:
                    print(f"[_resolve_credentials] RESOLVED via stored treatment_flow_phone_id: {stored_phone_id} for wa_id={wa_id}")
                    return tok, stored_phone_id
            # Check for lead phone_id in appointment_state
            lead_phone_id_appt = st.get("lead_phone_id")
            if lead_phone_id_appt and isinstance(WHATSAPP_NUMBERS, dict) and lead_phone_id_appt in WHATSAPP_NUMBERS:
                cfg = WHATSAPP_NUMBERS.get(lead_phone_id_appt) or {}
                tok = cfg.get("token")
                if tok:
                    print(f"[_resolve_credentials] RESOLVED via stored lead_phone_id (appointment_state): {lead_phone_id_appt} for wa_id={wa_id}")
                    return tok, lead_phone_id_appt
        except Exception:
            pass

    # 3) Check stored phone_id from lead appointment state (legacy)
    if wa_id:
        try:
            from controllers.web_socket import lead_appointment_state  # type: ignore
            lst = lead_appointment_state.get(wa_id) or {}
            lead_phone_id = lst.get("phone_id") or lst.get("lead_phone_id")
            if lead_phone_id and isinstance(WHATSAPP_NUMBERS, dict) and lead_phone_id in WHATSAPP_NUMBERS:
                cfg = WHATSAPP_NUMBERS.get(lead_phone_id) or {}
                tok = cfg.get("token")
                if tok:
                    print(f"[_resolve_credentials] RESOLVED via stored lead_phone_id (lead_appointment_state): {lead_phone_id} for wa_id={wa_id}")
                    return tok, lead_phone_id
        except Exception:
            pass

    # 4) Env-configured phone id
    env_pid = os.getenv("WHATSAPP_PHONE_ID")
    if env_pid and isinstance(WHATSAPP_NUMBERS, dict) and env_pid in WHATSAPP_NUMBERS:
        cfg = WHATSAPP_NUMBERS.get(env_pid) or {}
        tok = cfg.get("token")
        if tok:
            print(f"[_resolve_credentials] WARNING - FALLBACK to env WHATSAPP_PHONE_ID: {env_pid} for wa_id={wa_id} (no stored state found)")
            return tok, env_pid

    # 5) Single mapping entry
    try:
        entries = [(pid, cfg) for pid, cfg in (WHATSAPP_NUMBERS or {}).items() if (cfg or {}).get("token")]
        if len(entries) == 1:
            pid, cfg = entries[0]
            print(f"[_resolve_credentials] WARNING - FALLBACK to single WHATSAPP_NUMBERS entry: {pid} for wa_id={wa_id}")
            return cfg.get("token"), pid
    except Exception:
        pass

    # 6) Fallback to DB token + env phone id
    token_obj = whatsapp_service.get_latest_token(db)
    if token_obj and getattr(token_obj, "token", None):
        pid_final = (env_pid or os.getenv("WHATSAPP_PHONE_ID", "367633743092037"))
        print(f"[_resolve_credentials] WARNING - FALLBACK to DB token + default phone_id: {pid_final} for wa_id={wa_id}")
        return token_obj.token, pid_final
    raise HTTPException(status_code=400, detail="Token not available")

async def send_message_to_waid(wa_id: str, message_body: str, db, from_wa_id="917729992376", *, schedule_followup: bool = False, stage_label: str | None = None, phone_id_hint: str | None = None):
    access_token, phone_id = _resolve_credentials(db, hint_phone_id=phone_id_hint, wa_id=wa_id)
    try:
        print(f"[send_message_to_waid] phone_id={phone_id} wa_id={wa_id} len(body)={len(message_body)}")
    except Exception:
        pass
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": { "body": message_body }
    }

    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    try:
        j = res.json() if hasattr(res, "json") else None
        msg_ids = (j.get("messages") if isinstance(j, dict) else None) or []
        msg_id_preview = [m.get("id") for m in msg_ids]
        print(f"[send_message_to_waid] result status={res.status_code} phone_id={phone_id} message_ids={msg_id_preview}")
    except Exception:
        print(f"[send_message_to_waid] result status={res.status_code} phone_id={phone_id} text={(res.text[:200] if isinstance(res.text, str) else str(res.text))}")
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    # Pick display "from" number consistent with the phone_id we used
    try:
        display_from = from_wa_id
        if isinstance(WHATSAPP_NUMBERS, dict) and phone_id in WHATSAPP_NUMBERS:
            cfg = WHATSAPP_NUMBERS.get(phone_id) or {}
            # Extract only digits for consistency with other logs
            import re as _re
            digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
            display_from = digits or from_wa_id
        else:
            # fallback to env display
            display_from = os.getenv("WHATSAPP_DISPLAY_NUMBER", from_wa_id)
    except Exception:
        display_from = from_wa_id

    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=display_from,
        to_wa_id=wa_id,
        type="text",
        body=message_body,
        timestamp=datetime.now(),
        customer_id=customer.id,
    )
    new_msg = message_service.create_message(db, message_data)

    # Schedule a follow-up for outbound messages for treatment flow only.
    # CRITICAL: If schedule_followup=False is explicitly passed, do NOT schedule.
    # If schedule_followup=True is explicitly passed, DO schedule.
    # If schedule_followup is not provided (default False), check flow state:
    #   - If flow is completed, do NOT schedule
    #   - If not in lead appointment flow, schedule (default behavior)
    try:
        from services.followup_service import FOLLOW_UP_1_DELAY_MINUTES
        def _in_lead_flow(_wa_id: str) -> bool:
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                st = lead_appointment_state.get(_wa_id) or {}
                return bool(st) and (st.get("flow_context") == "lead_appointment")
            except Exception:
                return False

        # Check if flow is completed (final step reached)
        flow_completed = False
        try:
            from controllers.web_socket import appointment_state  # type: ignore
            st = appointment_state.get(wa_id) or {}
            flow_completed = st.get("flow_completed", False)
        except Exception:
            pass

        # Determine if we should schedule follow-up
        should_schedule = False
        if schedule_followup:
            # Explicitly requested to schedule
            should_schedule = True
        elif not schedule_followup and flow_completed:
            # Explicitly disabled OR flow completed - do NOT schedule
            should_schedule = False
        elif not _in_lead_flow(wa_id) and not flow_completed:
            # Default behavior: schedule if not in lead flow AND flow not completed
            should_schedule = True

        if should_schedule:
            schedule_next_followup(db, customer_id=customer.id, delay_minutes=FOLLOW_UP_1_DELAY_MINUTES, stage_label=stage_label)
    except Exception:
        pass
    
    # Debug: Print message details to verify saving
    print(f"[send_message_to_waid] DEBUG - Outbound message saved:")
    print(f"  - Message ID: {new_msg.message_id}")
    print(f"  - From: {new_msg.from_wa_id}")
    print(f"  - To: {new_msg.to_wa_id}")
    print(f"  - Type: {new_msg.type}")
    print(f"  - Body: {new_msg.body}")
    print(f"  - Timestamp: {new_msg.timestamp}")
    print(f"  - Customer ID: {new_msg.customer_id}")

    await manager.broadcast({
        "from": new_msg.from_wa_id,
        "to": new_msg.to_wa_id,
        "type": "text",
        "message": new_msg.body,
        "timestamp": new_msg.timestamp.isoformat(),
    })

    return new_msg


def _get_headers(db):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")
    return {
        "Authorization": f"Bearer {token_obj.token}",
        "Content-Type": "application/json"
    }


async def send_category_list(wa_id: str, db: Session):
    headers = _get_headers(db)
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    categories = db.query(Category).all()
    rows = []
    for c in categories:
        rows.append({
            "id": str(c.id),
            "title": c.name[:24],
            "description": (c.description or "")[:72]
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Browse Categories"},
            "body": {"text": "Choose a category"},
            "action": {
                "button": "Choose",
                "sections": [{
                    "title": "Categories",
                    "rows": rows or [{"id": "noop", "title": "No categories", "description": "Add from admin"}]
                }]
            }
        }
    }
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send categories: {res.text}")


async def send_subcategory_list(wa_id: str, category_id: str, db: Session):
    headers = _get_headers(db)
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    subs = db.query(SubCategory).filter(SubCategory.category_id == category_id).all()
    rows = []
    for s in subs:
        rows.append({
            "id": str(s.id),
            "title": s.name[:24],
            "description": (s.description or "")[:72]
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Subcategories"},
            "body": {"text": "Choose a subcategory"},
            "action": {
                "button": "Choose",
                "sections": [{
                    "title": "Subcategories",
                    "rows": rows or [{"id": f"cat:{category_id}", "title": "All items", "description": "No subcategories"}]
                }]
            }
        }
    }
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send subcategories: {res.text}")


async def send_products_list(wa_id: str, category_id: str = None, subcategory_id: str = None, db: Session = None):
    headers = _get_headers(db)
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
    q = db.query(Product)
    if subcategory_id:
        q = q.filter(Product.sub_category_id == subcategory_id)
    elif category_id:
        q = q.filter(Product.category_id == category_id)
    products = q.limit(10).all()
    rows = []
    for p in products:
        rows.append({
            "id": str(p.id),
            "title": p.name[:24],
            "description": f"₹{int(p.price)} | Stock: {p.stock}"
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Products"},
            "body": {"text": "Pick a product"},
            "action": {
                "button": "Choose",
                "sections": [{"title": "Products", "rows": rows or [{"id": "noop", "title": "No products available"}]}]
            }
        }
    }
    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send products: {res.text}")

async def send_location_to_waid(wa_id: str, latitude: float, longitude: float, name: str, address: str, db, from_wa_id="917729992376", phone_id_hint: str | None = None):
    access_token, phone_id = _resolve_credentials(db, hint_phone_id=phone_id_hint, wa_id=wa_id)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    location_data = {
        "latitude": latitude,
        "longitude": longitude,
    }
    if name:
        location_data["name"] = name
    if address:
        location_data["address"] = address

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "location",
        "location": location_data
    }

    res = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send location message: {res.text}")

    message_id = res.json()["messages"][0]["id"]
    customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))

    location_body = ", ".join(filter(None, [name, address]))

    message_data = MessageCreate(
        message_id=message_id,
        from_wa_id=from_wa_id,
        to_wa_id=wa_id,
        type="location",
        body=location_body,
        timestamp=datetime.now(),
        customer_id=customer.id,
        latitude=latitude,
        longitude=longitude,
    )
    new_msg = message_service.create_message(db, message_data)

    broadcast_data = {
        "from": new_msg.from_wa_id,
        "to": new_msg.to_wa_id,
        "type": "location",
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": new_msg.timestamp.isoformat(),
    }
    if name:
        broadcast_data["name"] = name
    if address:
        broadcast_data["address"] = address

    await manager.broadcast(broadcast_data)

    return new_msg