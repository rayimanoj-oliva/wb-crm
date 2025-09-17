import os
import requests


def update_variant_price(variant_id: str, new_price_inr: float) -> bool:
    """
    Update a Shopify product variant price via Admin REST API.

    Requires env:
      - SHOPIFY_SHOP (e.g., myshop.myshopify.com)
      - SHOPIFY_ADMIN_TOKEN (private app/Admin API access token)

    Args:
        variant_id: Shopify variant ID as string
        new_price_inr: New price in INR

    Returns:
        True if update succeeded, else False
    """
    shop = os.getenv("SHOPIFY_SHOP")
    token = os.getenv("SHOPIFY_ADMIN_TOKEN")
    if not shop or not token or not variant_id:
        return False

    try:
        url = f"https://{shop}/admin/api/2024-07/variants/{variant_id}.json"
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "variant": {
                "id": int(variant_id),
                "price": str(int(new_price_inr))
            }
        }
        resp = requests.put(url, json=payload, headers=headers, timeout=20)
        if resp.status_code in (200, 201):
            return True
        else:
            try:
                print("Shopify price update failed:", resp.status_code, resp.text)
            except Exception:
                pass
            return False
    except Exception as e:
        try:
            print("Shopify price update error:", e)
        except Exception:
            pass
        return False


