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

    params = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token",
    }

    response = requests.post(ZOHO_TOKEN_URL, params=params)

    data = response.json()
    return data["access_token"]
