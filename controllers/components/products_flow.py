from __future__ import annotations

from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from utils.whatsapp import send_products_list, send_message_to_waid


async def run_products_flow(
    db: Session,
    *,
    wa_id: str,
    category_id: Optional[str] = None,
    subcategory_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send products list to a WhatsApp ID, optionally filtered by category/subcategory.

    Returns a status dict.
    """

    await send_products_list(wa_id=wa_id, category_id=category_id, subcategory_id=subcategory_id, db=db)
    return {"status": "sent", "category_id": category_id, "subcategory_id": subcategory_id}



async def run_buy_products_flow(
    db: Session,
    *,
    wa_id: str,
    catalog_url: str = "https://wa.me/c/917729992376",
) -> Dict[str, Any]:
    """Send the catalog link used for the "Buy Products" quick action.

    Returns a status dict.
    """

    try:
        await send_message_to_waid(wa_id, f"🛍️ Browse our catalog: {catalog_url}", db)
        return {"status": "sent", "catalog_url": catalog_url}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


# ------------------------------
# Cart Next-Step (Modify/Cancel/Proceed)
# ------------------------------

from datetime import datetime
from typing import Any, Dict, Optional
import os
import requests
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url
from services import order_service
from utils.whatsapp import send_message_to_waid


async def send_cart_next_actions(db: Session, *, wa_id: str) -> Dict[str, Any]:
    """Send 3-button interactive: Modify, Cancel, Proceed.

    Returns a status dict.
    """

    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❗ Unable to show options right now. Please try again.", db)
            return {"status": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Would you like to modify your cart, cancel, or proceed?"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "modify_order", "title": "Modify"}},
                        {"type": "reply", "reply": {"id": "cancel_order", "title": "Cancel"}},
                        {"type": "reply", "reply": {"id": "proceed_order", "title": "Proceed"}},
                    ]
                },
            },
        }

        requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        return {"status": "sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200]}


async def handle_cart_next_action(
    db: Session,
    *,
    wa_id: str,
    reply_id: str,
    customer: Any,
) -> Dict[str, Any]:
    """Process replies: modify_order, cancel_order, proceed_order.

    - modify_order: show catalog again (preference-aware if possible)
    - cancel_order: acknowledge
    - proceed_order: send address_collection template
    """

    normalized = (reply_id or "").strip().lower()

    # Modify → show catalog again, with a Your Cart section if we can fetch it
    if normalized == "modify_order":
        try:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                await send_message_to_waid(wa_id, "Opening catalog...", db)
                from controllers.components.products_flow import run_buy_products_flow as _open_catalog
                await _open_catalog(db, wa_id=wa_id)
                return {"status": "catalog_link_sent"}

            access_token = token_entry.token
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

            # Try to fetch latest order items to show as a section
            your_cart_rows: list[Dict[str, str]] = []
            try:
                latest_order = (
                    db.query(order_service.Order)
                    .filter(order_service.Order.customer_id == customer.id)
                    .order_by(order_service.Order.timestamp.desc())
                    .first()
                )
                if latest_order and latest_order.items:
                    for it in latest_order.items[:10]:
                        if it.product_retailer_id:
                            your_cart_rows.append({"product_retailer_id": it.product_retailer_id})
            except Exception:
                pass

            sections = []
            if your_cart_rows:
                sections.append({
                    "title": "Your Cart",
                    "product_items": your_cart_rows,
                })
            # Generic section to allow adding more items
            sections.append({
                "title": "More Products",
                "product_items": [
                    {"product_retailer_id": "39302163202202"},
                    {"product_retailer_id": "39531958435994"},
                    {"product_retailer_id": "35404294455450"},
                    {"product_retailer_id": "35411030081690"},
                    {"product_retailer_id": "40286295392410"},
                ],
            })

            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "interactive",
                "interactive": {
                    "type": "product_list",
                    "header": {"type": "text", "text": "Modify your order"},
                    "body": {"text": "Review your cart and add more items if you like."},
                    "footer": {"text": "Tap to open the catalog"},
                    "action": {
                        "catalog_id": os.getenv("WHATSAPP_CATALOG_ID", "1093353131080785"),
                        "sections": sections,
                    },
                },
            }
            requests.post(get_messages_url(phone_id), headers=headers, json=payload)
            return {"status": "modify_catalog_sent"}
        except Exception:
            # Fallback to catalog link
            await run_buy_products_flow(db, wa_id=wa_id)
            return {"status": "catalog_link_sent"}

    # Cancel → simple acknowledgement for now
    if normalized == "cancel_order":
        try:
            await send_message_to_waid(wa_id, "❌ Your order request has been cancelled. You can browse again anytime.", db)
        except Exception:
            pass
        return {"status": "order_cancel_ack"}

    # Proceed → send address collection FLOW directly
    if normalized == "proceed_order":
        try:
            from controllers.web_socket import _send_address_flow_directly  # type: ignore
            await _send_address_flow_directly(wa_id, db, customer_id=getattr(customer, "id", None))
            return {"status": "address_flow_sent"}
        except Exception:
            pass
        # Do not send a text prompt; if flow fails, just return failure
        return {"status": "address_flow_failed"}

    return {"status": "skipped"}