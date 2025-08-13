import json
import uuid
import pika
import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.models import Campaign, Customer, Template, Job, Cost
from schemas.campaign_schema import CampaignCreate, CampaignUpdate
from uuid import UUID


# ---------- Campaign CRUD ----------

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
        type=campaign.type,  # "text" or "template"
        campaign_cost_type=campaign.campaign_cost_type,
        created_by=user_id,
        updated_by=user_id
    )
    db.add(new_campaign)

    if campaign.customer_ids:
        new_campaign.customers = db.query(Customer).filter(
            Customer.id.in_(campaign.customer_ids)
        ).all()

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


# ---------- Queue Helper ----------

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
        body=json.dumps(message, cls=EnhancedJSONEncoder),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()


# ---------- Run Campaign ----------

def run_campaign(campaign: Campaign, job: Job, db: Session):
    """
    Push campaign tasks to RabbitMQ for each customer.
    Supports both text and template campaigns.
    """
    for customer in campaign.customers:
        task = {
            "job_id": job.id,
            "campaign_id": campaign.id,
            "customer": {
                "id": str(customer.id),
                "name": customer.name,
                "wa_id": customer.wa_id
            },
            "type": campaign.type,
        }

        if campaign.type == "text":
            # Text message content is sent as-is
            task["content"] = {
                "preview_url": False,
                "body": campaign.content.get("body", "")
            }

        elif campaign.type == "template":
            # Template campaigns must have WhatsApp template structure
            task["content"] = {
                "name": campaign.content.get("name"),
                "language": campaign.content.get("language", {"code": "en_US"}),
                "components": campaign.content.get("components", [])
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported campaign type: {campaign.type}")

        publish_to_queue(task)

    return job
