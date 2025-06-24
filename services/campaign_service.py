from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.models import Campaign, Customer
from schemas.campaign_schema import CampaignCreate, CampaignUpdate
from uuid import UUID

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