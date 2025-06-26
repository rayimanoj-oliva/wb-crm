import json

import pika
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
import json
import uuid

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, uuid.UUID):
            return str(o)
        return super().default(o)

def publish_to_queue(message: dict, queue_name: str = "campaign_queue"):
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=queue_name,
        body=json.dumps(message,cls=EnhancedJSONEncoder),
        properties=pika.BasicProperties(
            delivery_mode=2,
        )
    )
    connection.close()

def run_campaign(campaign: Campaign, db: Session):
    for customer in campaign.customers:
        task = {
            "campaign_id": campaign.id,
            "customer": {
                "id": str(customer.id),
                "name": customer.name,
                "wa_id": customer.wa_id
            },
            "content": campaign.content,
            "type": campaign.type
        }
        publish_to_queue(task)
    return {"status": "queued","count": len(campaign.customers)}
