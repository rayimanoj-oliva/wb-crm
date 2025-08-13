from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from auth import get_current_user
from database.db import get_db
from schemas.campaign_schema import BulkTemplateRequest, CampaignOut, CampaignCreate, CampaignUpdate
from services import whatsapp_service, job_service
import services.campaign_service as campaign_service

router = APIRouter(tags=["Campaign"])

@router.post("/send-template")
def send_bulk_template(req: BulkTemplateRequest):
    """Directly queue sending a template message to multiple clients."""
    for client in req.clients:
        whatsapp_service.enqueue_template_message(
            to=client.wa_id,
            template_name=req.template_name,
            parameters=client.parameters
        )
    return {"status": "queued", "count": len(req.clients)}

@router.get("/", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """List all campaigns."""
    return campaign_service.get_all_campaigns(db)

@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):

    return campaign_service.get_campaign(db, campaign_id)

@router.post("/", response_model=CampaignOut)
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):

    return campaign_service.create_campaign(db, campaign, user_id=current_user.id)

@router.put("/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: UUID, updates: CampaignUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):

    return campaign_service.update_campaign(db, campaign_id, updates, user_id=current_user.id)

@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):

    return campaign_service.delete_campaign(db, campaign_id)

@router.post("/run/{campaign_id}")
def run_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):

    job = job_service.create_job(db, campaign_id, current_user)
    campaign = campaign_service.get_campaign(db, campaign_id)
    return campaign_service.run_campaign(campaign, job, db)
