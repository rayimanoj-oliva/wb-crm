from __future__ import annotations

# Central mapping of WhatsApp Business phone IDs to tokens and display names
# Replace the token values with your actual long-lived tokens

WHATSAPP_NUMBERS = {
    # Number 1
    "848542381673826": {
        "token": "EAAcbHJk0x70BOyGSMrMulAHKz9ZCtr0i8iOKbOgjp24Kvg4ZCZAzSeogfhH5iUhloDNpAjydOo7Ca4yOQzL23igIM3y898jOO9fN6L0iuCacW2tL53zSocr6KvTxfscej6ZABzBtRExE6PnNvCisIS8ZAiRveZAXhivoJ4hRKegHNMSBQZBjBVf70WqJ8etDZC2bOAZDZD",
        "name": "+91 82978 82978",
    },
    # Number 2
    "859830643878412": {
        "token": "EAAcbHJk0x70BOyGSMrMulAHKz9ZCtr0i8iOKbOgjp24Kvg4ZCZAzSeogfhH5iUhloDNpAjydOo7Ca4yOQzL23igIM3y898jOO9fN6L0iuCacW2tL53zSocr6KvTxfscej6ZABzBtRExE6PnNvCisIS8ZAiRveZAXhivoJ4hRKegHNMSBQZBjBVf70WqJ8etDZC2bOAZDZD",
        "name": "+91 76176 13030",
    },
}

# Treatment flow allowed phone IDs - only these two numbers can trigger the treatment flow
TREATMENT_FLOW_ALLOWED_PHONE_IDS = {
    "848542381673826",  # +91 82978 82978
    "859830643878412",  # +91 76176 13030
}


def get_number_config(phone_id: str) -> dict | None:
    """Return config for a given WhatsApp Business phone_id, if present."""
    return WHATSAPP_NUMBERS.get(phone_id)


