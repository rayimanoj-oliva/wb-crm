"""Centralized Graph API endpoints and helpers."""

WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/{phone_id}/messages"

def get_messages_url(phone_id: str) -> str:
    return WHATSAPP_API_URL.format(phone_id=phone_id)

def get_media_url(phone_id: str) -> str:
    return f"https://graph.facebook.com/v22.0/{phone_id}/media"
