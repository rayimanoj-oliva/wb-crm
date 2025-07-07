import httpx
import os

ZENOTI_API_URL = "https://api.zenoti.com/v1/guests/search"

async def search_guest_by_phone(phone: str):
    headers = {
        "Authorization": f"apikey {os.getenv('ZENOTI_API_KEY')}",
        "accept": "application/json"
    }
    params = {"phone": phone}
    async with httpx.AsyncClient() as client:
        response = await client.get(ZENOTI_API_URL, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
