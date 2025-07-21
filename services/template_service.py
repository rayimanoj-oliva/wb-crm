from http.client import HTTPException

import requests
from fastapi.params import Depends
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import Template
from schemas.template_schema import TemplateCreate, TemplateUpdate, TemplatesResponse, CreateMetaTemplateRequest
from services.whatsapp_service import get_latest_token
from utils.json_placeholder import fill_placeholders

def union_dict(dic1,dic2):
    for i in dic1:
        dic2[i] = dic1[i]
    return dic2
def send_template_to_customer(template_name,extra, db: Session = Depends(get_db)):
    token_entry = get_latest_token(db)

    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    url = f"{WHATSAPP_API_URL}"
    headers = {
        "Authorization": f"Bearer {token_entry.token}",
        "Content-Type": "application/json"
    }

    template = db.query(Template).filter(Template.template_name == template_name).first()
    new_vars = union_dict(extra, template.template_vars)
    new_body = fill_placeholders(template.template_body, new_vars)
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to":extra["customer_phone"],
        "type": "template",
        "template": new_body
    }

    response = requests.post(url, headers=headers, json=data)
    return response.json()

def create_template(db: Session, template: TemplateCreate):
    db_template = Template(**template.dict())
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

def get_template(db: Session, template_name: str):
    return db.query(Template).filter(Template.template_name == template_name).first()

def get_all_templates(db: Session):
    return db.query(Template).all()

def update_template(db: Session, template_name: str, template_data: TemplateUpdate):
    db_template = get_template(db, template_name)
    if db_template:
        for field, value in template_data.dict().items():
            setattr(db_template, field, value)
        db.commit()
        db.refresh(db_template)
    return db_template

def delete_template(db: Session, template_name: str):
    db_template = get_template(db, template_name)
    if db_template:
        db.delete(db_template)
        db.commit()
    return db_template

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
