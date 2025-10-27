"""
Zoho Mapping Service
Handles mapping between treatment concerns and Zoho CRM names
"""

from sqlalchemy.orm import Session
from models.models import ZohoMapping
from typing import Optional, Dict, Any


def get_zoho_mapping(db: Session, treatment_name: str) -> Optional[ZohoMapping]:
    """
    Get Zoho mapping for a given treatment name.
    
    Args:
        db: Database session
        treatment_name: The treatment name to look up
    
    Returns:
        ZohoMapping if found, None otherwise
    """
    return db.query(ZohoMapping).filter(
        ZohoMapping.treatment_name == treatment_name
    ).first()


def get_zoho_name(db: Session, treatment_name: str) -> str:
    """
    Get Zoho name for a given treatment name.
    Falls back to the treatment name if no mapping exists.
    
    Args:
        db: Database session
        treatment_name: The treatment name to look up
    
    Returns:
        Zoho name or treatment name if not found
    """
    mapping = get_zoho_mapping(db, treatment_name)
    if mapping:
        return mapping.zoho_name
    return treatment_name


def get_zoho_mapping_info(db: Session, treatment_name: str) -> Dict[str, Any]:
    """
    Get complete Zoho mapping information including sub-concern.
    
    Args:
        db: Database session
        treatment_name: The treatment name to look up
    
    Returns:
        Dictionary with zoho_name and zoho_sub_concern
    """
    mapping = get_zoho_mapping(db, treatment_name)
    if mapping:
        return {
            "zoho_name": mapping.zoho_name,
            "zoho_sub_concern": mapping.zoho_sub_concern
        }
    return {
        "zoho_name": treatment_name,
        "zoho_sub_concern": None
    }


def create_zoho_mapping(
    db: Session,
    treatment_name: str,
    zoho_name: str,
    zoho_sub_concern: Optional[str] = None
) -> ZohoMapping:
    """
    Create a new Zoho mapping.
    
    Args:
        db: Database session
        treatment_name: The treatment name
        zoho_name: The corresponding Zoho name
        zoho_sub_concern: Optional sub-concern
    
    Returns:
        Created ZohoMapping
    """
    mapping = ZohoMapping(
        treatment_name=treatment_name,
        zoho_name=zoho_name,
        zoho_sub_concern=zoho_sub_concern
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


def update_zoho_mapping(
    db: Session,
    treatment_name: str,
    zoho_name: str,
    zoho_sub_concern: Optional[str] = None
) -> ZohoMapping:
    """
    Update an existing Zoho mapping.
    
    Args:
        db: Database session
        treatment_name: The treatment name
        zoho_name: The corresponding Zoho name
        zoho_sub_concern: Optional sub-concern
    
    Returns:
        Updated ZohoMapping
    """
    mapping = get_zoho_mapping(db, treatment_name)
    if mapping:
        mapping.zoho_name = zoho_name
        if zoho_sub_concern:
            mapping.zoho_sub_concern = zoho_sub_concern
        db.commit()
        db.refresh(mapping)
        return mapping
    else:
        return create_zoho_mapping(db, treatment_name, zoho_name, zoho_sub_concern)


def list_all_mappings(db: Session) -> list[ZohoMapping]:
    """
    List all Zoho mappings.
    
    Args:
        db: Database session
    
    Returns:
        List of all ZohoMapping objects
    """
    return db.query(ZohoMapping).all()

