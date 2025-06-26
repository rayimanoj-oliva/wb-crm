from http.client import HTTPException

import requests
from fastapi.params import Depends
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import Template
from schemas.template_schema import TemplateCreate, TemplateUpdate
from services.whatsapp_service import get_latest_token
from utils.json_placeholder import fill_placeholders

def union_dict(dic1,dic2):
    for i in dic2:
        dic1[i] = dic2[i]
    return dic1
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
    print(new_body)
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