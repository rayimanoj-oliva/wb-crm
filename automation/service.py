from sqlalchemy.orm import Session
from .models import (
    ReplyMaterial, DefaultAutomationRule, Keyword, KeywordTerm, KeywordReply, RoutingRule, WorkingHour, HolidayConfig
)
from .schemas import *
from uuid import UUID
from typing import List, Optional

# --- Reply Material ---
def create_reply_material(db: Session, material: ReplyMaterialCreate) -> ReplyMaterial:
    db_material = ReplyMaterial(**material.dict())
    db.add(db_material)
    db.commit()
    db.refresh(db_material)
    return db_material

def get_reply_materials(db: Session, type: Optional[str] = None, search: Optional[str] = None) -> List[ReplyMaterial]:
    query = db.query(ReplyMaterial)
    if type:
        query = query.filter(ReplyMaterial.type == type)
    if search:
        query = query.filter(ReplyMaterial.title.ilike(f"%{search}%"))
    return query.all()

def get_reply_material(db: Session, material_id: UUID) -> Optional[ReplyMaterial]:
    return db.query(ReplyMaterial).filter(ReplyMaterial.id == material_id).first()

def update_reply_material(db: Session, material_id: UUID, material: ReplyMaterialUpdate) -> Optional[ReplyMaterial]:
    db_material = get_reply_material(db, material_id)
    if not db_material:
        return None
    for field, value in material.dict(exclude_unset=True).items():
        setattr(db_material, field, value)
    db.commit()
    db.refresh(db_material)
    return db_material

def delete_reply_material(db: Session, material_id: UUID) -> bool:
    db_material = get_reply_material(db, material_id)
    if not db_material:
        return False
    db.delete(db_material)
    db.commit()
    return True

# --- Default Automation Rule ---
def get_all_default_rules(db: Session) -> List[DefaultAutomationRule]:
    return db.query(DefaultAutomationRule).all()

def update_default_rule(db: Session, rule_id: UUID, rule: DefaultAutomationRuleUpdate) -> Optional[DefaultAutomationRule]:
    db_rule = db.query(DefaultAutomationRule).filter(DefaultAutomationRule.id == rule_id).first()
    if not db_rule:
        return None
    for field, value in rule.dict(exclude_unset=True).items():
        setattr(db_rule, field, value)
    db.commit()
    db.refresh(db_rule)
    return db_rule

# --- Keyword Actions ---
def create_keyword(db: Session, keyword: KeywordCreate) -> Keyword:
    db_keyword = Keyword(matching_type=keyword.matching_type, trigger_count=keyword.trigger_count)
    db.add(db_keyword)
    db.commit()
    # Add terms
    for term in keyword.terms:
        db_term = KeywordTerm(keyword_id=db_keyword.id, value=term.value)
        db.add(db_term)
    # Add replies
    for reply in keyword.replies:
        db_reply = KeywordReply(keyword_id=db_keyword.id, material_id=reply.material_id)
        db.add(db_reply)
    db.commit()
    db.refresh(db_keyword)
    return db_keyword

def get_keyword(db: Session, keyword_id: UUID) -> Optional[Keyword]:
    return db.query(Keyword).filter(Keyword.id == keyword_id).first()

def get_keywords(db: Session) -> List[Keyword]:
    return db.query(Keyword).all()

def update_keyword(db: Session, keyword_id: UUID, keyword: KeywordUpdate) -> Optional[Keyword]:
    db_keyword = get_keyword(db, keyword_id)
    if not db_keyword:
        return None
    for field, value in keyword.dict(exclude_unset=True).items():
        if field in ["terms", "replies"]:
            continue  # handled separately
        setattr(db_keyword, field, value)
    db.commit()
    # Update terms if provided
    if keyword.terms is not None:
        db.query(KeywordTerm).filter(KeywordTerm.keyword_id == keyword_id).delete()
        for term in keyword.terms:
            db_term = KeywordTerm(keyword_id=keyword_id, value=term.value)
            db.add(db_term)
    # Update replies if provided
    if keyword.replies is not None:
        db.query(KeywordReply).filter(KeywordReply.keyword_id == keyword_id).delete()
        for reply in keyword.replies:
            db_reply = KeywordReply(keyword_id=keyword_id, material_id=reply.material_id)
            db.add(db_reply)
    db.commit()
    db.refresh(db_keyword)
    return db_keyword

def delete_keyword(db: Session, keyword_id: UUID) -> bool:
    db_keyword = get_keyword(db, keyword_id)
    if not db_keyword:
        return False
    db.delete(db_keyword)
    db.commit()
    return True

# --- Routing Rule ---
def create_routing_rule(db: Session, rule: RoutingRuleCreate) -> RoutingRule:
    db_rule = RoutingRule(**rule.dict())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def get_routing_rules(db: Session) -> List[RoutingRule]:
    return db.query(RoutingRule).all()

def get_routing_rule(db: Session, rule_id: UUID) -> Optional[RoutingRule]:
    return db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()

def update_routing_rule(db: Session, rule_id: UUID, rule: RoutingRuleUpdate) -> Optional[RoutingRule]:
    db_rule = get_routing_rule(db, rule_id)
    if not db_rule:
        return None
    for field, value in rule.dict(exclude_unset=True).items():
        setattr(db_rule, field, value)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def delete_routing_rule(db: Session, rule_id: UUID) -> bool:
    db_rule = get_routing_rule(db, rule_id)
    if not db_rule:
        return False
    db.delete(db_rule)
    db.commit()
    return True

# --- Working Hours ---
def get_working_hours(db: Session) -> List[WorkingHour]:
    return db.query(WorkingHour).all()

def update_working_hour(db: Session, working_hour_id: UUID, wh: WorkingHourUpdate) -> Optional[WorkingHour]:
    db_wh = db.query(WorkingHour).filter(WorkingHour.id == working_hour_id).first()
    if not db_wh:
        return None
    for field, value in wh.dict(exclude_unset=True).items():
        setattr(db_wh, field, value)
    db.commit()
    db.refresh(db_wh)
    return db_wh

# --- Holiday Config ---
def get_holiday_config(db: Session) -> HolidayConfig:
    config = db.query(HolidayConfig).first()
    if not config:
        config = HolidayConfig(id=1, holiday_mode=0)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

def update_holiday_config(db: Session, holiday_mode: bool) -> HolidayConfig:
    config = get_holiday_config(db)
    config.holiday_mode = 1 if holiday_mode else 0
    db.commit()
    db.refresh(config)
    return config 