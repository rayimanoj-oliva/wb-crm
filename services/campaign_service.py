import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import WHATSAPP_API_URL
from models.models import Campaign, Customer, Template
from schemas.campaign_schema import CampaignCreate, CampaignUpdate
from uuid import UUID

from services import whatsapp_service
from services.template_service import union_dict
from utils.json_placeholder import fill_placeholders


def get_all_campaigns(db: Session):
    return db.query(Campaign).all()

def get_campaign(db: Session, campaign_id: UUID):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

def create_campaign(db: Session, campaign: CampaignCreate, user_id: UUID):
    new_campaign = Campaign(
        name=campaign.name,
        description=campaign.description,
        content=campaign.content,
        type=campaign.type,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(new_campaign)

    if campaign.customer_ids:
        new_campaign.customers = db.query(Customer).filter(Customer.id.in_(campaign.customer_ids)).all()

    print(new_campaign.customers)
    db.commit()
    db.refresh(new_campaign)
    return new_campaign

def update_campaign(db: Session, campaign_id: UUID, updates: CampaignUpdate, user_id: UUID):
    campaign = get_campaign(db, campaign_id)
    for field, value in updates.dict(exclude_unset=True).items():
        if field == "customer_ids":
            campaign.customers = db.query(Customer).filter(Customer.id.in_(value)).all()
        else:
            setattr(campaign, field, value)
    campaign.updated_by = user_id
    db.commit()
    db.refresh(campaign)
    return campaign

def delete_campaign(db: Session, campaign_id: UUID):
    campaign = get_campaign(db, campaign_id)
    db.delete(campaign)
    db.commit()
    return {"detail": "Campaign deleted"}

def run_campaign(campaign: Campaign,db: Session):
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    headers = {"Authorization": f"Bearer {token}"}
    for customer in campaign.customers:
        extra = {
            "customer_id": str(customer.id),
            "customer_name": customer.name,
            "customer_phone": customer.wa_id,
        }
        if campaign.type != "template":
            payload = {
                "messaging_product": "whatsapp",
                "to": customer.wa_id,
                "recipient_type": "individual",
                "type": campaign.type,
                campaign.type:campaign.content
            }
        else:
            template_name = campaign.content['template_name']
            template = db.query(Template).filter(Template.template_name == template_name).first()

            new_vars = union_dict(extra, template.template_vars)
            new_body = fill_placeholders(template.template_body, new_vars)
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": extra["customer_phone"],
                "type": "template",
                "template": new_body
            }
        res = requests.post(
            WHATSAPP_API_URL,
            json=payload,
            headers={**headers, "Content-Type": "application/json"}
        )
        print(res)
    return {}
