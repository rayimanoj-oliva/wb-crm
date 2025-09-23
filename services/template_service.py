from fastapi import HTTPException

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

def create_template_on_meta(payload: CreateMetaTemplateRequest, db: Session):
    token_entry = get_latest_token(db)

    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    url = "https://graph.facebook.com/v22.0/286831244524604/message_templates"
    headers = {
        "Authorization": f"Bearer {token_entry.token}",
        "Content-Type": "application/json"
    }

    request_body = {
        "name": payload.name,
        "language": payload.language,
        "category": payload.category,
        "components": [component.dict(exclude_none=True) for component in payload.components]
    }

    response = requests.post(url, headers=headers, json=request_body)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json())

    return response.json()

import requests
from typing import Dict, Any

TEMPLATE_API_URL = "https://graph.facebook.com/v22.0/286831244524604/message_templates"


def upsert_template_record(db: Session, *, template_name: str, template_body: Dict, template_vars: Dict) -> Template:
    existing = db.query(Template).filter(Template.template_name == template_name).first()
    if existing:
        existing.template_body = template_body
        existing.template_vars = template_vars or existing.template_vars or {}
        db.commit()
        db.refresh(existing)
        return existing
    rec = Template(template_name=template_name, template_body=template_body, template_vars=template_vars or {})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

def send_template_to_facebook(payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
    token_entry = get_latest_token(db)
    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    token = token_entry.token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = requests.post(TEMPLATE_API_URL, json=payload, headers=headers)
    response.raise_for_status()
    result = response.json()

    # Persist to DB as well
    try:
        template_name = payload.get("name") or result.get("name")
        upsert_template_record(db, template_name=template_name, template_body=payload, template_vars={})
    except Exception:
        # Don't break API if persistence fails; log in real env
        pass

    return result

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


def sync_templates_from_meta_to_db(db: Session) -> Dict[str, Any]:
    meta_resp = get_all_templates_from_meta(db)
    created = 0
    updated = 0
    for item in meta_resp.data:
        template_name = item.name
        body = {
            "name": item.name,
            "language": item.language,
            "status": item.status,
            "category": item.category,
            "components": [c.model_dump() for c in (item.components or [])],
        }
        existed = db.query(Template).filter(Template.template_name == template_name).first() is not None
        upsert_template_record(db, template_name=template_name, template_body=body, template_vars={})
        if existed:
            updated += 1
        else:
            created += 1
    return {"status": "ok", "created": created, "updated": updated, "total": len(meta_resp.data)}