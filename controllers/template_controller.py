
from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.orm import Session

from database.db import get_db
from schemas.template_schema import TemplatesResponse, CreateMetaTemplateRequest, TemplateStructure
from services.template_service import get_all_templates_from_meta, create_template_on_meta, send_template_to_facebook

router = APIRouter(tags=["Templates"])
@router.get("/meta", response_model=TemplatesResponse)
def fetch_meta_templates(db: Session = Depends(get_db)):
    return get_all_templates_from_meta(db)


@router.post("/")
def create_template(template: TemplateStructure, db: Session = Depends(get_db)):
    try:
        response = send_template_to_facebook(template.root,db)
        # print(template)
        return {"status": "success", "facebook_response": response}
        return template.root
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))