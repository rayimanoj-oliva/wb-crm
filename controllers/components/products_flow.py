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

