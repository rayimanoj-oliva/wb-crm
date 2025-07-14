from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from database.db import get_db
from schemas.campaign_schema import BulkTemplateRequest, CampaignOut, CampaignCreate, CampaignUpdate
from schemas.cost_schema import CostOut
from services import whatsapp_service, job_service
import services.campaign_service as campaign_service

from models.models import Cost, Campaign

router = APIRouter(tags=["Campaign"])

@router.post("/send-template")
def send_bulk_template(req: BulkTemplateRequest):
    for client in req.clients:
        whatsapp_service.enqueue_template_message(
            to=client.wa_id,
            template_name=req.template_name,
            parameters=client.parameters
        )
    return {"status": "queued", "count": len(req.clients)}

@router.get("/", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.get_all_campaigns(db)

@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.get_campaign(db, campaign_id)

@router.post("/", response_model=CampaignOut)
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.create_campaign(db, campaign, user_id=current_user.id)

@router.put("/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: UUID, updates: CampaignUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.update_campaign(db, campaign_id, updates, user_id=current_user["id"])

@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.delete_campaign(db, campaign_id)

@router.post("/run/{campaign_id}")
def run_campaign(campaign_id: UUID, db: Session = Depends(get_db)):
    job = job_service.create_job(db, campaign_id)
    campaign = campaign_service.get_campaign(db, campaign_id)
    return campaign_service.run_campaign(campaign, job, db)


# ------------------- ✅ NEW: CAMPAIGN TYPE (COST TYPE) ENDPOINTS ------------------- #

@router.get("/types", response_model=List[CostOut])
def get_all_campaign_types(db: Session = Depends(get_db)):
    return db.query(Cost).all()

@router.get("/types/{type_name}", response_model=CostOut)
def get_campaign_type_detail(type_name: str, db: Session = Depends(get_db)):
    cost = db.query(Cost).filter(Cost.type == type_name).first()
    if not cost:
        raise HTTPException(status_code=404, detail="Campaign type not found")
    return cost

@router.get("/types/{type_name}/count")
def count_campaigns_by_type(type_name: str, db: Session = Depends(get_db)):
    count = db.query(Campaign).filter(Campaign.campaign_cost_type == type_name).count()
    return {"type": type_name, "campaign_count": count}
