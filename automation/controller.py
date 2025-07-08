from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from database.db import get_db
from auth import get_current_user
from models.models import User
from . import service
from .schemas import *

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

# --- Routing Rules ---
@router.post("/automation/routing", response_model=RoutingRuleOut, tags=["Routing"])
def create_routing_rule(rule: RoutingRuleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.create_routing_rule(db, rule)

@router.get("/automation/routing", response_model=List[RoutingRuleOut], tags=["Routing"])
def list_routing_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.get_routing_rules(db)

@router.get("/automation/routing/{rule_id}", response_model=RoutingRuleOut, tags=["Routing"])
def get_routing_rule(rule_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rule = service.get_routing_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    return rule

@router.put("/automation/routing/{rule_id}", response_model=RoutingRuleOut, tags=["Routing"])
def update_routing_rule(rule_id: UUID, rule: RoutingRuleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = service.update_routing_rule(db, rule_id, rule)
    if not updated:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    return updated

@router.delete("/automation/routing/{rule_id}", tags=["Routing"])
def delete_routing_rule(rule_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not service.delete_routing_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="Routing rule not found")
    return {"ok": True}

# --- Working Hours ---
@router.get("/automation/working-hours", response_model=List[WorkingHourOut], tags=["Working Hours"])
def get_working_hours(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.get_working_hours(db)

@router.put("/automation/working-hours/{working_hour_id}", response_model=WorkingHourOut, tags=["Working Hours"])
def update_working_hour(working_hour_id: UUID, wh: WorkingHourUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    updated = service.update_working_hour(db, working_hour_id, wh)
    if not updated:
        raise HTTPException(status_code=404, detail="Working hour not found")
    return updated

# --- Holiday Config ---
@router.get("/automation/holiday", response_model=HolidayConfigOut, tags=["Working Hours"])
def get_holiday_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.get_holiday_config(db)

@router.put("/automation/holiday", response_model=HolidayConfigOut, tags=["Working Hours"])
def update_holiday_config(update: HolidayConfigUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return service.update_holiday_config(db, update.holiday_mode) 