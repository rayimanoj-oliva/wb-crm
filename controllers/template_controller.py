from http.client import HTTPException
from typing import List
from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session

from database.db import get_db
from models.models import Template
from schemas.template_schema import TemplateCreate, TemplateOut, TemplateUpdate
from services import template_service
from services.customer_service import get_customer_by_id
from services.template_service import send_template_to_customer
from uuid import UUID
router = APIRouter(tags=["Templates"])

@router.post("/", response_model=TemplateOut, status_code=201)
def create_template(template: TemplateCreate, db: Session = Depends(get_db)):
    existing = template_service.get_template(db, template.template_name)
    if existing:
        raise HTTPException(status_code=409, detail="Template already exists")
    return template_service.create_template(db, template)

@router.get("/{template_name}", response_model=TemplateOut)
def read_template(template_name: str, db: Session = Depends(get_db)):
    template = template_service.get_template(db, template_name)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template

@router.get("/", response_model=List[TemplateOut])
def read_all_templates(db: Session = Depends(get_db)):
    return template_service.get_all_templates(db)

@router.put("/{template_name}", response_model=TemplateOut)
def update_template(template_name: str, template_data: TemplateUpdate, db: Session = Depends(get_db)):
    updated = template_service.update_template(db, template_name, template_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Template not found")
    return updated

@router.delete("/{template_name}", status_code=204)
def delete_template(template_name: str, db: Session = Depends(get_db)):
    deleted = template_service.delete_template(db, template_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return

@router.post("/{customer_id}/{template_name}")
def send_template(customer_id: UUID, template_name: str, db: Session = Depends(get_db)):
    customer = get_customer_by_id(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    extra = {
        "customer_id": str(customer.id),
        "customer_name": customer.name,
        "customer_phone": customer.wa_id,
    }

    try:
        result = send_template_to_customer(template_name, extra, db)
        return {"message": "Template sent successfully", "response": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")