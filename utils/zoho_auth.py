import os
import requests
from dotenv import load_dotenv

load_dotenv()

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
ZOHO_TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"

_access_token_cache = {
    "access_token": None,
    "expires_at": 0,
}

import time

def get_valid_access_token():
    """Return a fresh Zoho OAuth access_token, raising a clear error if refresh fails."""
    # Basic validation of required env vars
    missing = [
        name for name, val in [
            ("ZOHO_CLIENT_ID", ZOHO_CLIENT_ID),
            ("ZOHO_CLIENT_SECRET", ZOHO_CLIENT_SECRET),
            ("ZOHO_REFRESH_TOKEN", ZOHO_REFRESH_TOKEN),
        ] if not val
    ]
    if missing:
        raise RuntimeError(f"Missing Zoho OAuth env vars: {', '.join(missing)}")

    params = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token",
    }

    resp = requests.post(ZOHO_TOKEN_URL, params=params, timeout=30)

    # Handle HTTP errors explicitly
    if resp.status_code != 200:
        try:
            body = resp.text
        except Exception:
            body = "<unavailable>"
        raise RuntimeError(f"Zoho token refresh failed: {resp.status_code} {body}")

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError("Zoho token refresh returned non-JSON body")

    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Zoho token refresh response missing access_token: {data}")
    return token
