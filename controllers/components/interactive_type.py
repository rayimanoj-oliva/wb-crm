from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import os
import re
import requests
from sqlalchemy.orm import Session

from config.constants import get_messages_url
from services import message_service, order_service
from services.whatsapp_service import get_latest_token
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def run_interactive_type(
    db: Session,
    *,
    message: Dict[str, Any],
    interactive: Dict[str, Any],
    i_type: str,
    timestamp: datetime,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    wa_id: str,
    customer: Any,
) -> Dict[str, Any]:
    """Handle WhatsApp interactive payloads (flow, form, button_reply, list_reply).

    Returns a status dict. If not handled, returns {"status": "skipped"}.
    """

    # 1) Flow submission (e.g., address collection)
    if i_type == "flow":
        flow_response = interactive.get("flow_response", {})
        flow_id = (flow_response.get("flow_id", "") or "")
        flow_cta = flow_response.get("flow_cta", "")
        flow_action_payload = flow_response.get("flow_action_payload", {})

        try:
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "flow_response",
                "flow_id": flow_id,
                "flow_cta": flow_cta,
                "payload": flow_action_payload,
                "timestamp": timestamp.isoformat(),
            })
        except Exception:
            pass

        if (flow_id == "address_collection_flow") or ("address" in flow_id.lower()):
            try:
                # Extract address data
                address_data: Dict[str, Any] = {}
                if flow_action_payload:
                    field_mappings = {
                        "full_name": ["full_name", "name", "customer_name"],
                        "phone_number": ["phone_number", "phone", "mobile"],
                        "house_street": ["house_street", "address_line_1", "street"],
                        "locality": ["locality", "area", "neighborhood"],
                        "city": ["city", "town"],
                        "state": ["state", "province"],
                        "pincode": ["pincode", "postal_code", "zip_code"],
                        "landmark": ["landmark", "landmark_nearby"],
                    }
                    for field_name, possible_keys in field_mappings.items():
                        for key in possible_keys:
                            if key in flow_action_payload:
                                address_data[field_name] = flow_action_payload[key]
                                break

                # Validate & save
                if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                    from schemas.address_schema import CustomerAddressCreate
                    from services.address_service import create_customer_address

                    address_create = CustomerAddressCreate(
                        customer_id=customer.id,
                        full_name=address_data.get("full_name", ""),
                        house_street=address_data.get("house_street", ""),
                        locality=address_data.get("locality", ""),
                        city=address_data.get("city", ""),
                        state=address_data.get("state", ""),
                        pincode=address_data.get("pincode", ""),
                        landmark=address_data.get("landmark", ""),
                        phone=address_data.get("phone_number", customer.wa_id),
                        address_type="home",
                        is_default=True,
                    )
                    saved_address = create_customer_address(db, address_create)

                    await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                    await send_message_to_waid(
                        wa_id,
                        f"📍 {saved_address.full_name}, {saved_address.house_street}, {saved_address.locality}, {saved_address.city} - {saved_address.pincode}",
                        db,
                    )

                    # Clear awaiting address flag if present (best-effort; ignore if missing)
                    try:
                        from controllers.web_socket import awaiting_address_users  # type: ignore
                        awaiting_address_users[wa_id] = False
                    except Exception:
                        pass

                    # Continue with payment flow (best-effort)
                    try:
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        total_amount = 0
                        if latest_order:
                            for item in latest_order.items:
                                qty = item.quantity or 1
                                price = item.item_price or item.price or 0
                                total_amount += float(price) * int(qty)
                        if total_amount > 0:
                            from utils.razorpay_utils import create_razorpay_payment_link
                            try:
                                payment_resp = create_razorpay_payment_link(
                                    amount=float(total_amount),
                                    currency="INR",
                                    description=f"WA Order {str(latest_order.id) if latest_order else ''}",
                                )
                                pay_link = payment_resp.get("short_url") if isinstance(payment_resp, dict) else None
                                if pay_link:
                                    await send_message_to_waid(wa_id, f"💳 Please complete your payment using this link: {pay_link}", db)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    return {"status": "address_saved", "message_id": message_id}
                else:
                    await send_message_to_waid(
                        wa_id,
                        "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).",
                        db,
                    )
                    return {"status": "flow_incomplete", "message_id": message_id}
            except Exception as e:
                await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                return {"status": "flow_error", "message_id": message_id}

        return {"status": "flow_processed", "message_id": message_id}

    # 2) Form submission (address_form)
    if i_type == "form":
        form_response = interactive.get("form_response", {})
        form_name = form_response.get("name", "")
        form_data = form_response.get("data", [])
        if form_name == "address_form":
            try:
                address_data: Dict[str, Any] = {}
                for item in form_data:
                    field_id = item.get("id", "")
                    field_value = item.get("value", "")
                    address_data[field_id] = field_value

                if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                    from schemas.address_schema import CustomerAddressCreate
                    from services.address_service import create_customer_address

                    address_create = CustomerAddressCreate(
                        customer_id=customer.id,
                        full_name=address_data.get("full_name", ""),
                        house_street=address_data.get("house_street", ""),
                        locality=address_data.get("locality", ""),
                        city=address_data.get("city", ""),
                        state=address_data.get("state", ""),
                        pincode=address_data.get("pincode", ""),
                        landmark=address_data.get("landmark", ""),
                        phone=address_data.get("phone_number", customer.wa_id),
                        address_type="home",
                        is_default=True,
                    )
                    saved_address = create_customer_address(db, address_create)

                    await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                    await send_message_to_waid(
                        wa_id,
                        f"📍 {saved_address.full_name}, {saved_address.house_street}, {saved_address.locality}, {saved_address.city} - {saved_address.pincode}",
                        db,
                    )

                    # Clear awaiting address flag if present
                    try:
                        from controllers.web_socket import awaiting_address_users  # type: ignore
                        awaiting_address_users[wa_id] = False
                    except Exception:
                        pass

                    # Payment hint (existing logic sends link later)
                    try:
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        total_amount = 0
                        if latest_order:
                            for item in latest_order.items:
                                qty = item.quantity or 1
                                price = item.item_price or item.price or 0
                                total_amount += float(price) * int(qty)
                        if total_amount > 0:
                            await send_message_to_waid(
                                wa_id,
                                f"💳 Please complete your payment of ₹{int(total_amount)} using the payment link that will be sent shortly.",
                                db,
                            )
                    except Exception:
                        pass

                    return {"status": "address_saved", "message_id": message_id}
                else:
                    await send_message_to_waid(wa_id, "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).", db)
                    return {"status": "form_incomplete", "message_id": message_id}
            except Exception:
                await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                return {"status": "form_error", "message_id": message_id}

        # Not an address form; let caller handle further
        return {"status": "skipped"}

    # 3) Persist button/list replies early and delegate treatment buttons to existing flow
    try:
        if i_type in {"button_reply", "list_reply"}:
            title = interactive.get("button_reply", {}).get("title") if i_type == "button_reply" else interactive.get("list_reply", {}).get("title")
            reply_id = interactive.get("button_reply", {}).get("id") if i_type == "button_reply" else interactive.get("list_reply", {}).get("id")
            reply_text_any = (title or reply_id or "[Interactive Reply]")
            msg_interactive_any = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="interactive",
                body=reply_text_any,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, msg_interactive_any)
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "interactive",
                "message": reply_text_any,
                "timestamp": timestamp.isoformat(),
            })

            # Delegate skin/hair/body and next actions
            from controllers.components.treament_flow import run_treatment_buttons_flow  # local import to avoid cycles
            flow_result = await run_treatment_buttons_flow(
                db,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                message_id=message_id,
                btn_id=reply_id,
                btn_text=title,
            )
            if (flow_result or {}).get("status") in {"list_sent", "hair_template_sent", "body_template_sent", "next_actions_sent"}:
                return flow_result
    except Exception:
        pass

    return {"status": "skipped"}


