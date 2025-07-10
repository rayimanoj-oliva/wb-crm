import requests
from .zenoti_client import search_guest_by_phone

ZENOTI_API_URL = "https://api.zenoti.com/v1/centers"
ZENOTI_API_KEY = "f5bd053c34de47c686d2a0f35e68c136e7539811437e4749915b48e725d40eca"

# ---------------------------
# Get Guest Details by Phone
# ---------------------------
async def get_guest_details(phone: str):
    full_response = await search_guest_by_phone(phone)
    guests = full_response.get("guests", [])

    if not guests:
        return {"address_info": None}

    address_info = guests[0].get("address_info", None)
    return {"address_info": address_info}


# ---------------------------
# Fetch Center Names with IDs
# ---------------------------
def fetch_center_names():
    try:
        response = requests.get(
            ZENOTI_API_URL,
            headers={
                "Authorization": f"apikey {ZENOTI_API_KEY}",
                "accept": "application/json"
            },
            params={
                "catalog_enabled": "false",
                "expand": "working_hours"
            }
        )
        response.raise_for_status()
        data = response.json()
        centers = data.get("centers", [])

        return [
            {
                "center_id": center.get("id"),
                "center_name": center.get("name")
            }
            for center in centers
            if center.get("id") and center.get("name")
        ]

    except requests.exceptions.RequestException as e:
        raise Exception(f"Error fetching centers: {str(e)}")
