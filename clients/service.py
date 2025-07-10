import requests

from clients.schema import AppointmentQuery, CollectionQuery, SalesQuery

ZENOTI_API_KEY = "f5bd053c34de47c686d2a0f35e68c136e7539811437e4749915b48e725d40eca"
COLLECTION_BASE_URL = "https://oliva.zenoti.com/api/v100/services/integration/collectionsapi.aspx"

def fetch_appointments(query: AppointmentQuery):
    url = "https://api.zenoti.com/v1/appointments"
    headers = {
        "Authorization": f"apikey {ZENOTI_API_KEY}",
        "accept": "application/json"
    }
    params = query.dict()
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def fetch_walkins(appointment_id: str):
    url = f"https://api.zenoti.com/v1/appointments/{appointment_id}"
    headers = {
        "Authorization": f"apikey {ZENOTI_API_KEY}",
        "accept": "application/json"
    }
    params = {
        "view_context": 1,
        "version_no": 0,
        "tag_id":None
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def fetch_collections(query: CollectionQuery):
    params = {
        "userName": "apisetup",
        "userPassword": "Password123",
        "accountName": "oliva",
        "appVersion": "v100",
        "methodName": "getCollectionsReport",
        "centerid": query.centerid,
        "fromdate": str(query.fromdate),
        "todate": str(query.todate),
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.get(COLLECTION_BASE_URL, params=params, headers=headers)
    return response.json()

def fetch_sales(query: SalesQuery):
    url = "https://api.zenoti.com/v1/sales/salesreport"
    headers = {
        "Authorization": "apikey <your api key>",
        "accept": "application/json"
    }
    response = requests.get(url, headers=headers, params=query.dict())
    return response.json()

def fetch_leads():
    # Placeholder: logic for Zoho or CRM system to be implemented
    return {"message": "Lead fetching not yet implemented."}
