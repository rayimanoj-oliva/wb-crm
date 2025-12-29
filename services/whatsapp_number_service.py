"""
WhatsApp Number service for business logic
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_
from uuid import UUID

from models.models import WhatsAppNumber, Organization
from schemas.whatsapp_number_schema import WhatsAppNumberCreate, WhatsAppNumberUpdate


def create_whatsapp_number(db: Session, whatsapp_number_data: WhatsAppNumberCreate) -> WhatsAppNumber:
    """Create a new WhatsApp number mapping"""
    # Verify organization exists
    organization = db.query(Organization).filter(Organization.id == whatsapp_number_data.organization_id).first()
    if not organization:
        raise ValueError(f"Organization with id '{whatsapp_number_data.organization_id}' not found")
    
    # Check if phone_number_id already exists
    existing = db.query(WhatsAppNumber).filter(
        WhatsAppNumber.phone_number_id == whatsapp_number_data.phone_number_id
    ).first()
    if existing:
        raise ValueError(f"WhatsApp number with phone_number_id '{whatsapp_number_data.phone_number_id}' already exists")
    
    whatsapp_number = WhatsAppNumber(
        phone_number_id=whatsapp_number_data.phone_number_id,
        display_number=whatsapp_number_data.display_number,
        access_token=whatsapp_number_data.access_token,
        webhook_path=whatsapp_number_data.webhook_path,
        organization_id=whatsapp_number_data.organization_id,
        is_active=whatsapp_number_data.is_active
    )
    
    db.add(whatsapp_number)
    db.commit()
    db.refresh(whatsapp_number)
    return whatsapp_number


def get_whatsapp_number(db: Session, whatsapp_number_id: UUID) -> Optional[WhatsAppNumber]:
    """Get WhatsApp number by ID"""
    return db.query(WhatsAppNumber).filter(WhatsAppNumber.id == whatsapp_number_id).first()


def get_whatsapp_number_by_phone_id(db: Session, phone_number_id: str) -> Optional[WhatsAppNumber]:
    """Get WhatsApp number by phone_number_id (Meta's phone ID)"""
    return db.query(WhatsAppNumber).filter(WhatsAppNumber.phone_number_id == phone_number_id).first()


def get_whatsapp_numbers(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    organization_id: Optional[UUID] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None
) -> tuple[List[WhatsAppNumber], int]:
    """Get list of WhatsApp numbers with filtering"""
    query = db.query(WhatsAppNumber)
    
    if organization_id:
        query = query.filter(WhatsAppNumber.organization_id == organization_id)
    
    if is_active is not None:
        query = query.filter(WhatsAppNumber.is_active == is_active)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                WhatsAppNumber.phone_number_id.ilike(search_pattern),
                WhatsAppNumber.display_number.ilike(search_pattern),
                WhatsAppNumber.webhook_path.ilike(search_pattern)
            )
        )
    
    # Order by created_at descending (newest first)
    query = query.order_by(WhatsAppNumber.created_at.desc())
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    whatsapp_numbers = query.offset(skip).limit(limit).all()
    
    return whatsapp_numbers, total


def update_whatsapp_number(
    db: Session,
    whatsapp_number_id: UUID,
    whatsapp_number_data: WhatsAppNumberUpdate
) -> Optional[WhatsAppNumber]:
    """Update a WhatsApp number"""
    whatsapp_number = get_whatsapp_number(db, whatsapp_number_id)
    if not whatsapp_number:
        return None
    
    # If organization_id is being updated, verify it exists
    if whatsapp_number_data.organization_id:
        organization = db.query(Organization).filter(Organization.id == whatsapp_number_data.organization_id).first()
        if not organization:
            raise ValueError(f"Organization with id '{whatsapp_number_data.organization_id}' not found")
    
    # Update fields
    update_data = whatsapp_number_data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(whatsapp_number, field, value)
    
    db.commit()
    db.refresh(whatsapp_number)
    return whatsapp_number


def delete_whatsapp_number(db: Session, whatsapp_number_id: UUID) -> bool:
    """Delete a WhatsApp number"""
    whatsapp_number = get_whatsapp_number(db, whatsapp_number_id)
    if not whatsapp_number:
        return False
    
    db.delete(whatsapp_number)
    db.commit()
    return True


def get_organization_by_phone_id(db: Session, phone_number_id: str) -> Optional[Organization]:
    """Get organization by WhatsApp phone_number_id (used in webhooks)"""
    whatsapp_number = get_whatsapp_number_by_phone_id(db, phone_number_id)
    if not whatsapp_number or not whatsapp_number.is_active:
        return None
    
    return whatsapp_number.organization

