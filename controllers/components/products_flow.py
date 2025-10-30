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
    print(f"[DEBUG] run_buy_products_flow triggered for {wa_id}")
    """Send the catalog link used for the "Buy Products" quick action.

    Returns a status dict.
    """

    try:
        print(f"[DEBUG] Sending catalogue to {wa_id}: {catalog_url}")
        await send_message_to_waid(wa_id, f"🛍️ Browse our catalog: {catalog_url}", db)
        return {"status": "sent", "catalog_url": catalog_url}
    except Exception as e:
        print(f"[DEBUG][ERROR] Exception in run_buy_products_flow: {e}")
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

        response = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        # Save to database and broadcast to WebSocket if message was sent successfully
        if response.status_code == 200:
            try:
                # Get message ID from response
                response_data = response.json()
                message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                
                # Get or create customer
                from services.customer_service import get_or_create_customer
                from schemas.customer_schema import CustomerCreate
                customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                
                # Save outbound message to database
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Would you like to modify your cart, cancel, or proceed?",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[products_flow] DEBUG - Outbound message saved to database: {message_id}")
                
                # Broadcast to WebSocket
                from utils.ws_manager import manager
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Would you like to modify your cart, cancel, or proceed?",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "buttons",
                        "options": ["Modify", "Cancel", "Proceed"]
                    }
                })
            except Exception as e:
                print(f"[products_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
        
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
    # Removed wa_id restriction; cart summary is sent for every cart for all wa_ids.
    normalized = (reply_id or "").strip().lower()

    # Modify → show catalog again, with a Your Cart section if we can fetch it
    if normalized == "modify_order":
        print(f"[products_flow] DEBUG - Processing modify_order for wa_id: {wa_id}")
        print(f"[products_flow] DEBUG - Customer: {customer}")
        
        try:
            token_entry = get_latest_token(db)
            if not token_entry or not token_entry.token:
                print(f"[products_flow] DEBUG - No token available, falling back to catalog link")
                await send_message_to_waid(wa_id, "Opening catalog...", db)
                from controllers.components.products_flow import run_buy_products_flow as _open_catalog
                await _open_catalog(db, wa_id=wa_id)
                return {"status": "catalog_link_sent"}

            access_token = token_entry.token
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

            # Try to fetch latest order items - always show all items in cart
            cart_rows: list[Dict[str, str]] = []
            all_selected_product_ids: set[str] = set()
            
            try:
                latest_order = (
                    db.query(order_service.Order)
                    .filter(order_service.Order.customer_id == customer.id)
                    .order_by(order_service.Order.timestamp.desc())
                    .first()
                )
                
                print(f"[products_flow] DEBUG - Latest order found: {latest_order is not None}")
                if latest_order:
                    print(f"[products_flow] DEBUG - Order has {len(latest_order.items)} items")
                    print(f"[products_flow] DEBUG - Order modification_started_at: {latest_order.modification_started_at}")
                
                if latest_order and latest_order.items:
                    # Show ALL items in the cart (both original and new items)
                    for it in latest_order.items[:10]:  # Limit to 10 items
                        if it.product_retailer_id:
                            item_data = {"product_retailer_id": it.product_retailer_id}
                            all_selected_product_ids.add(it.product_retailer_id)
                            cart_rows.append(item_data)
                            
            except Exception as e:
                print(f"[products_flow] ERROR - Failed to fetch order items: {str(e)}")
                pass

            sections = []
            
            # Always show cart items if they exist
            if cart_rows:
                sections.append({
                    "title": "Your Cart",
                    "product_items": cart_rows,
                })
            
            # Generic section to allow adding more items (exclude already selected)
            available_products = [
                {"product_retailer_id": "39302163202202"},
                {"product_retailer_id": "39531958435994"},
                {"product_retailer_id": "35404294455450"},
                {"product_retailer_id": "35411030081690"},
                {"product_retailer_id": "40286295392410"},
            ]
            
            # Filter out products that are already in the cart
            filtered_products = [
                product for product in available_products 
                if product["product_retailer_id"] not in all_selected_product_ids
            ]
            
            if filtered_products:  # Only add section if there are products to show
                sections.append({
                    "title": "Add More",
                    "product_items": filtered_products,
                })
            
            # If no cart items exist, show all available products
            if not cart_rows:
                sections.append({
                    "title": "Available Products",
                    "product_items": available_products,
                })
            
            # Debug logging
            print(f"[products_flow] DEBUG - Sections count: {len(sections)}")
            print(f"[products_flow] DEBUG - Cart items: {len(cart_rows)}")
            print(f"[products_flow] DEBUG - All selected product IDs: {all_selected_product_ids}")
            print(f"[products_flow] DEBUG - Available products: {len(available_products)}")
            print(f"[products_flow] DEBUG - Filtered products: {len(filtered_products)}")
            print(f"[products_flow] DEBUG - Filtered product IDs: {[p['product_retailer_id'] for p in filtered_products]}")

            # Ensure we always have at least one section
            if not sections:
                sections.append({
                    "title": "Available Products",
                    "product_items": available_products,
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "interactive",
                "interactive": {
                    "type": "product_list",
                    "header": {"type": "text", "text": "Modify Your Order"},
                    "body": {"text": "Your selected items are shown below. You can add more products."},
                    "footer": {"text": "Tap to view and add items"},
                    "action": {
                        "catalog_id": os.getenv("WHATSAPP_CATALOG_ID", "1093353131080785"),
                        "sections": sections,
                    },
                },
            }
            
            response = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
            
            # Log response for debugging
            print(f"[products_flow] DEBUG - Modify order response status: {response.status_code}")
            if response.status_code != 200:
                print(f"[products_flow] ERROR - Modify order failed: {response.text}")
            
            # Save to database and broadcast to WebSocket if message was sent successfully
            if response.status_code == 200:
                try:
                    # Get message ID from response
                    response_data = response.json()
                    message_id = response_data.get("messages", [{}])[0].get("id", f"outbound_{datetime.now().timestamp()}")
                    
                    # Get or create customer
                    from services.customer_service import get_or_create_customer
                    from schemas.customer_schema import CustomerCreate
                    customer = get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=""))
                    
                    # Save outbound message to database
                    from services.message_service import create_message
                    from schemas.message_schema import MessageCreate
                    
                    outbound_message = MessageCreate(
                        message_id=message_id,
                        from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                        to_wa_id=wa_id,
                        type="interactive",
                        body="Modify Your Order - Your selected items are shown below. You can add more products.",
                        timestamp=datetime.now(),
                        customer_id=customer.id,
                    )
                    create_message(db, outbound_message)
                    print(f"[products_flow] DEBUG - Modify order message saved to database: {message_id}")
                    
                    # Broadcast to WebSocket
                    from utils.ws_manager import manager
                    await manager.broadcast({
                        "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                        "to": wa_id,
                        "type": "interactive",
                        "message": "Modify Your Order - Your selected items are shown below. You can add more products.",
                        "timestamp": datetime.now().isoformat(),
                        "meta": {
                            "kind": "product_list",
                            "sections": sections
                        }
                    })
                except Exception as e:
                    print(f"[products_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            
            return {"status": "modify_catalog_sent"}
        except Exception as e:
            print(f"[products_flow] ERROR - Modify order failed with exception: {str(e)}")
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


def _matches_any(val, keywords):
    if not val:
        return False
    check_val = val.strip().lower()
    return any(kw in check_val for kw in keywords)

async def route_product_flow(
    db: Session,
    message: dict,
    interactive: dict,
    i_type: str,
    timestamp: datetime,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    wa_id: str,
    customer: Any
) -> Optional[dict]:
    """
    Route all Buy Products/catalogue/cart triggers.
    Used by the main interactive router to delegate all product flows cleanly.
    """
    buy_keywords = {"buy_products", "buy product", "buy products", "show catalogue", "catalogue", "catalog", "browse products"}
    cart_triggers = {"modify_order", "cancel_order", "proceed_order"}
    input_fields = [
        interactive.get("button_reply", {}).get("id"),
        interactive.get("button_reply", {}).get("title"),
        interactive.get("list_reply", {}).get("id"),
        interactive.get("list_reply", {}).get("title"),
        message.get("message"),
    ]
    # Early return for Buy/Catalogue
    for val in input_fields:
        if _matches_any(val, buy_keywords):
            print(f"[route_product_flow] Detected catalogue/buy trigger: {val}")
            return await run_buy_products_flow(db, wa_id=wa_id)
    # Check for cart actions
    reply_id = interactive.get("button_reply", {}).get("id") or interactive.get("list_reply", {}).get("id")
    if reply_id and _matches_any(reply_id, cart_triggers):
        print(f"[route_product_flow] Routing cart action: {reply_id}")
        return await handle_cart_next_action(db, wa_id=wa_id, reply_id=reply_id, customer=customer)
    return None