"""
Controller for Zoho Mapping API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from database.db import get_db
from services.zoho_mapping_service import (
    get_zoho_name,
    get_zoho_mapping_info,
    create_zoho_mapping,
    update_zoho_mapping,
    list_all_mappings
)
from models.models import ZohoMapping

router = APIRouter()


class ZohoMappingCreate(BaseModel):
    treatment_name: str
    zoho_name: str
    zoho_sub_concern: str = None


class ZohoMappingUpdate(BaseModel):
    zoho_name: str
    zoho_sub_concern: str = None


class ZohoMappingResponse(BaseModel):
    id: str
    treatment_name: str
    zoho_name: str
    zoho_sub_concern: str = None

    class Config:
        from_attributes = True


@router.get("/zoho-mappings", response_model=List[ZohoMappingResponse])
async def list_mappings(db: Session = Depends(get_db)):
    """List all Zoho mappings"""
    mappings = list_all_mappings(db)
    return mappings


@router.post("/zoho-mappings", response_model=ZohoMappingResponse)
async def create_mapping(data: ZohoMappingCreate, db: Session = Depends(get_db)):
    """Create a new Zoho mapping"""
    try:
        mapping = create_zoho_mapping(
            db=db,
            treatment_name=data.treatment_name,
            zoho_name=data.zoho_name,
            zoho_sub_concern=data.zoho_sub_concern
        )
        return mapping
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/zoho-mappings/{treatment_name}", response_model=ZohoMappingResponse)
async def update_mapping(
    treatment_name: str,
    data: ZohoMappingUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing Zoho mapping"""
    try:
        mapping = update_zoho_mapping(
            db=db,
            treatment_name=treatment_name,
            zoho_name=data.zoho_name,
            zoho_sub_concern=data.zoho_sub_concern
        )
        return mapping
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/zoho-mappings/lookup/{treatment_name}")
async def lookup_zoho_name(treatment_name: str, db: Session = Depends(get_db)):
    """Lookup Zoho name for a treatment name"""
    mapping_info = get_zoho_mapping_info(db, treatment_name)
    return mapping_info

