import os
from dotenv import load_dotenv

load_dotenv()

ZENOTI_API_KEY = os.getenv("ZENOTI_API_KEY")  

ZENOTI_HEADERS = {
    "Authorization": f"apikey {ZENOTI_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

BASE_URL = "https://api.zenoti.com/v1"
