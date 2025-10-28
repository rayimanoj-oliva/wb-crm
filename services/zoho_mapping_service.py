"""
Zoho Mapping Service
Handles mapping between treatment concerns and Zoho CRM names
"""

from sqlalchemy.orm import Session
from models.models import ZohoMapping
from typing import Optional, Dict, Any


def _canonicalize_treatment_name(raw_name: Optional[str]) -> Optional[str]:
    """Normalize various incoming labels/ids to the canonical DB treatment_name."""
    if not raw_name:
        return raw_name
    try:
        txt = (raw_name or "").strip()
        # Strip category prefixes like "Skin:", "Hair:", "Body:"
        lowered = txt.lower()
        for prefix in ("skin:", "hair:", "body:"):
            if lowered.startswith(prefix):
                txt = txt[len(prefix):].strip()
                lowered = txt.lower()
                break

        import re as _re
        canon = _re.sub(r"[^a-z0-9]+", " ", lowered).strip()
        synonyms = {
            "acne": "Acne / Acne Scars",
            "acne acne scars": "Acne / Acne Scars",
            "pigmentation": "Pigmentation & Uneven Skin Tone",
            "uneven skin tone": "Pigmentation & Uneven Skin Tone",
            "anti aging": "Anti-Aging & Skin Rejuvenation",
            "skin rejuvenation": "Anti-Aging & Skin Rejuvenation",
            "dandruff": "Dandruff & Scalp Care",
            "dandruff scalp care": "Dandruff & Scalp Care",
            "laser hair removal": "Laser Hair Removal",
            "hair loss hair fall": "Hair Loss / Hair Fall",
            "hair transplant": "Hair Transplant",
            "weight management": "Weight Management",
            "body contouring": "Body Contouring",
            "weight loss": "Weight Loss",
            "other skin concerns": "Other Skin Concerns",
            "other hair concerns": "Other Hair Concerns",
            "other body concerns": "Other Body Concerns",
        }
        return synonyms.get(canon, raw_name)
    except Exception:
        return raw_name


def _fix_zoho_name_typos(zoho_name: Optional[str]) -> Optional[str]:
    """Hotfix for known data typos in the mapping table without changing DB now."""
    if not zoho_name:
        return zoho_name
    if zoho_name == "Skin Cocnern":
        return "Skin Concerns"
    if zoho_name == "Dark Cirlce":
        return "Dark Circle"
    if zoho_name == "Anti Aeging":
        return "Anti Aging"
    return zoho_name


def get_zoho_mapping(db: Session, treatment_name: str) -> Optional[ZohoMapping]:
    """
    Get Zoho mapping for a given treatment name.
    
    Args:
        db: Database session
        treatment_name: The treatment name to look up
    
    Returns:
        ZohoMapping if found, None otherwise
    """
    canonical = _canonicalize_treatment_name(treatment_name)
    mapping = db.query(ZohoMapping).filter(
        ZohoMapping.treatment_name == (canonical or treatment_name)
    ).first()
    return mapping


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
        return _fix_zoho_name_typos(mapping.zoho_name)
    # As a fallback, return canonicalized label if we have it
    canonical = _canonicalize_treatment_name(treatment_name)
    return canonical or treatment_name


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
            "zoho_name": _fix_zoho_name_typos(mapping.zoho_name),
            "zoho_sub_concern": mapping.zoho_sub_concern
        }
    canonical = _canonicalize_treatment_name(treatment_name)
    return {
        "zoho_name": canonical or treatment_name,
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

