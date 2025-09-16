import requests
from fastapi.params import Depends
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import WHATSAPP_API_URL
from database import db
from database.db import get_db
from models.models import Template
from schemas.template_schema import TemplateCreate, TemplateUpdate, TemplatesResponse, CreateMetaTemplateRequest
from services.whatsapp_service import get_latest_token
from utils.json_placeholder import fill_placeholders
from fastapi import HTTPException

def get_all_templates_from_meta(db: Session = Depends(get_db)) -> TemplatesResponse:
    token_entry = get_latest_token(db)
    print(token_entry)
    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    page_id = "286831244524604"
    url = f"https://graph.facebook.com/v22.0/{page_id}/message_templates"
    headers = {
        "Authorization": f"Bearer {token_entry.token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json())

    return TemplatesResponse(**response.json())

WHATSAPP_GRAPH_URL = "https://graph.facebook.com/v22.0"
def create_template_on_meta(payload: CreateMetaTemplateRequest, db: Session):
    """
    Creates a WhatsApp template on Meta.
    """
    print(payload)
    token_entry = get_latest_token(db)

    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    url = f"{WHATSAPP_GRAPH_URL}/367633743092037/message_templates"   # TODO: make phone_id dynamic from DB/env
    headers = {
        "Authorization": f"Bearer {token_entry.token}",
        "Content-Type": "application/json"
    }

    # Serialize request body from Pydantic schema
    request_body = payload

    try:
        response = requests.post(url, headers=headers, json=request_body)
        response_data = response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error contacting Meta API: {str(e)}")

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response_data)

    return response_data

import requests
from typing import Dict, Any

TEMPLATE_API_URL = "https://graph.facebook.com/v22.0/367633743092037/message_templates"

def send_template_to_facebook(payload: Dict[str, Any],db: Session) -> Dict[str, Any]:

    token_entry = get_latest_token(db)
    if not token_entry:
        return HTTPException(status=404)

    token = token_entry.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        TEMPLATE_API_URL,
        json=payload,
        headers=headers
    )

    response.raise_for_status()
    return response.json()

def delete_template_from_meta(template_name: str, db: Session):
    token_entry = get_latest_token(db)
    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    page_id = "286831244524604"  # Replace with dynamic value if needed
    url = f"https://graph.facebook.com/v22.0/{page_id}/message_templates"
    headers = {
        "Authorization": f"Bearer {token_entry.token}"
    }

    params = {"name": template_name}

    response = requests.delete(url, headers=headers, params=params)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json())

    return {"status": "success", "detail": response.json()}