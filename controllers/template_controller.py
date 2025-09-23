
from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.orm import Session

from database.db import get_db
from schemas.template_schema import TemplatesResponse, CreateMetaTemplateRequest, TemplateStructure
from models.models import Template
from services.template_service import (
    get_all_templates_from_meta,
    create_template_on_meta,
    send_template_to_facebook,
    delete_template_from_meta,
    sync_templates_from_meta_to_db,
)

router = APIRouter(tags=["Templates"])
@router.get("/meta", response_model=TemplatesResponse)
def fetch_meta_templates(db: Session = Depends(get_db)):
    return get_all_templates_from_meta(db)


@router.post("/")
def create_template(template: TemplateStructure, db: Session = Depends(get_db)):
    try:
        response = send_template_to_facebook(template.root, db)
        return {"status": "success", "facebook_response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/")
def delete_template(template_name: str, db: Session = Depends(get_db)):
    try:
        result = delete_template_from_meta(template_name, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
def sync_templates(db: Session = Depends(get_db)):
    try:
        return sync_templates_from_meta_to_db(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/local")
def list_local_templates(db: Session = Depends(get_db)):
    items = db.query(Template).all()
    return items