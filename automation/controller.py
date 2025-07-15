from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
import os, shutil
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from database.db import get_db
from auth import get_current_user
from models.models import User
from . import service
from .schemas import *
import os, shutil
UPLOAD_DIR = "uploads/reply_materials"
router = APIRouter()

# --- Reply Materials ---
@router.post("/automation/materials", response_model=ReplyMaterialOut, tags=["Reply Materials"])
def create_reply_material(material: ReplyMaterialCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.create_reply_material(db, material)

@router.get("/automation/materials", response_model=List[ReplyMaterialOut], tags=["Reply Materials"])
def list_reply_materials(type: Optional[str] = Query(None), search: Optional[str] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.get_reply_materials(db, type, search)

@router.get("/automation/materials/{material_id}", response_model=ReplyMaterialOut, tags=["Reply Materials"])
def get_reply_material(material_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    material = service.get_reply_material(db, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return material

@router.put("/automation/materials/{material_id}", response_model=ReplyMaterialOut, tags=["Reply Materials"])
def update_reply_material(material_id: UUID, material: ReplyMaterialUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = service.update_reply_material(db, material_id, material)
    if not updated:
        raise HTTPException(status_code=404, detail="Material not found")
    return updated

@router.delete("/automation/materials/{material_id}", tags=["Reply Materials"])
def delete_reply_material(material_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not service.delete_reply_material(db, material_id):
        raise HTTPException(status_code=404, detail="Material not found")
    return {"ok": True}

@router.post("/automation/materials/upload", tags=["Reply Materials"])
def upload_reply_material_file(
    title: str = Form(...),
    type: str = Form(...),  # Accept type: 'image' or 'document'
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    url = f"/{UPLOAD_DIR}/{file.filename}"
    content = {"url": url, "filename": file.filename}
    material = service.create_reply_material(db, ReplyMaterialCreate(
        type=type,
        title=title,
        content=content,
        preview=url
    ))
    return material

@router.get("/automation/materials/file/{filename}", tags=["Reply Materials"])
def get_reply_material_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/octet-stream", filename=filename)

# --- Default Automation Rules ---
@router.get("/automation/default-rules", response_model=List[DefaultAutomationRuleOut], tags=["Automation Rules"])
def get_default_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.get_all_default_rules(db)

@router.put("/automation/default-rules/{rule_id}", response_model=DefaultAutomationRuleOut, tags=["Automation Rules"])
def update_default_rule(rule_id: UUID, rule: DefaultAutomationRuleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = service.update_default_rule(db, rule_id, rule)
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found")
    return updated

# --- Keyword Actions ---
@router.post("/automation/keywords", response_model=KeywordOut, tags=["Keyword Actions"])
def create_keyword(keyword: KeywordCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.create_keyword(db, keyword)

@router.get("/automation/keywords", response_model=List[KeywordOut], tags=["Keyword Actions"])
def list_keywords(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.get_keywords(db)

@router.get("/automation/keywords/{keyword_id}", response_model=KeywordOut, tags=["Keyword Actions"])
def get_keyword(keyword_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    keyword = service.get_keyword(db, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return keyword

@router.put("/automation/keywords/{keyword_id}", response_model=KeywordOut, tags=["Keyword Actions"])
def update_keyword(keyword_id: UUID, keyword: KeywordUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = service.update_keyword(db, keyword_id, keyword)
    if not updated:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return updated

@router.delete("/automation/keywords/{keyword_id}", tags=["Keyword Actions"])
def delete_keyword(keyword_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not service.delete_keyword(db, keyword_id):
        raise HTTPException(status_code=404, detail="Keyword not found")
    return {"ok": True}

@router.post("/automation/keyword-replies", tags=["Keyword Actions"])
def associate_keyword_replies_endpoint(req: KeywordRepliesAssociationRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service.associate_keyword_replies(db, req.keyword_id, req.material_ids)
    return {"ok": True}


# --- Working Hours ---
@router.get("/automation/working-hours", response_model=List[WorkingHourOut], tags=["Working Hours"])
def get_working_hours(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = service.get_working_hours(db)
    out = []
    for r in result:
        intervals = []
        for interval in r.intervals:
            if isinstance(interval, dict) and 'from_time' in interval and 'to_time' in interval:
                intervals.append({'from': interval['from_time'], 'to': interval['to_time']})
            else:
                intervals.append(interval)
        out.append(WorkingHourOut(
            id=r.id,
            day=r.day,
            open=r.open,
            intervals=intervals
        ))
    return out

@router.put("/automation/working-hours/{working_hour_id}", response_model=WorkingHourOut, tags=["Working Hours"])
def update_working_hour(working_hour_id: UUID, wh: WorkingHourUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = service.update_working_hour(db, working_hour_id, wh)
    if not updated:
        raise HTTPException(status_code=404, detail="Working hour not found")
    intervals = []
    for interval in updated.intervals:
        if isinstance(interval, dict) and 'from_time' in interval and 'to_time' in interval:
            intervals.append({'from': interval['from_time'], 'to': interval['to_time']})
        else:
            intervals.append(interval)
    return WorkingHourOut(
        id=updated.id,
        day=updated.day,
        open=updated.open,
        intervals=intervals
    )

