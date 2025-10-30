from fastapi import APIRouter
from fastapi.responses import RedirectResponse
import urllib.parse

router = APIRouter()

WHATSAPP_NUMBER = "917729992376"
CLINIC_MESSAGES = {
    "jubileehills": "Hi, Oliva! I want to know more about services in Jubilee Hills, Hyderabad clinic.",
    "banjarahills": "Hi, Oliva! I want to know more about services in Banjara Hills, Hyderabad clinic.",
    "kukatpally": "Hi, Oliva! I want to know more about services in Kukatpally, Hyderabad clinic.",
    "kondapur": "Hi, Oliva! I want to know more about services in Kondapur, Hyderabad clinic.",
    "gachibowli": "Hi, Oliva! I want to know more about services in Gachibowli, Hyderabad clinic.",
    "dwarakanagar": "Hi, Oliva! I want to know more about services in Dwaraka Nagar, Visakhapatnam clinic.",
}

@router.get("/wa/{clinic_name}")
async def redirect_to_whatsapp(clinic_name: str):
    message = CLINIC_MESSAGES.get(
        clinic_name.lower(),
        "Hi, Oliva! I want to know more about your dermatology services."
    )
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={encoded_message}"
    return RedirectResponse(url=whatsapp_url)
