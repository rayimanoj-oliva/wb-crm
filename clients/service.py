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
        "tag_id": None
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
        "Authorization": f"apikey {ZENOTI_API_KEY}",
        "accept": "application/json"
    }
    response = requests.get(url, headers=headers, params=query.dict())
    return response.json()

def fetch_leads():
    url = "https://www.zohoapis.in/crm/v2.1/coql"
    headers = {
        "Authorization": "Bearer 1000.1c48bdba152aab531a673befba522b62.3928034f990cce01333a60ff69459c66",
        "Content-Type": "application/json"
    }
    payload = {
        "select_query": """
            select Last_Name, Email, Mobile, Phone 
            from Leads 
            where (Created_Time between '2022-01-24T01:56:37+05:30' and '2022-01-24T03:56:37+05:30') 
            ORDER BY id ASC LIMIT 1,200
        """
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        return {
            "error": "Failed to fetch leads",
            "status_code": response.status_code,
            "details": response.text
        }

    try:
        result = response.json()
        data = result.get("data", [])  # return only the list of leads
        response = []
        for item in data:
            if item.get("Mobile") or item.get("Phone"):
                response.append(item)

        return response
    except Exception as e:
        return {"error": "Failed to parse leads", "details": str(e)}
