"""
WhatsApp Number controller for API endpoints
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.db import get_db
from models.models import User
from schemas.whatsapp_number_schema import (
    WhatsAppNumberCreate,
    WhatsAppNumberUpdate,
    WhatsAppNumberResponse,
    WhatsAppNumberListResponse
)
from services import whatsapp_number_service
from auth import get_current_user, get_current_super_admin, get_current_admin_user

router = APIRouter(prefix="/whatsapp-numbers", tags=["WhatsApp Numbers"])


@router.post("/", response_model=WhatsAppNumberResponse, status_code=201)
def create_whatsapp_number(
    whatsapp_number_data: WhatsAppNumberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new WhatsApp number mapping (Admin only)"""
    try:
        whatsapp_number = whatsapp_number_service.create_whatsapp_number(db, whatsapp_number_data)
        return whatsapp_number
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create WhatsApp number: {str(e)}")


@router.get("/", response_model=WhatsAppNumberListResponse)
def list_whatsapp_numbers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    organization_id: Optional[UUID] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List WhatsApp numbers (filtered by organization if not super admin)"""
    # Filter by organization if user is not super admin
    user_org_id = None
    is_super_admin = False
    
    # Check if user has SUPER_ADMIN role
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
    
    if not is_super_admin and hasattr(current_user, 'role') and current_user.role:
        role_str = str(current_user.role).upper()
        if role_str in ["SUPER_ADMIN", "ADMIN"]:
            is_super_admin = True
    
    # Non-super admins can only see WhatsApp numbers for their organization
    if not is_super_admin:
        user_org_id = current_user.organization_id
        if not user_org_id:
            return WhatsAppNumberListResponse(items=[], total=0)
    
    # Use user's organization_id if not super admin, otherwise use provided organization_id
    filter_org_id = user_org_id if not is_super_admin else organization_id
    
    whatsapp_numbers, total = whatsapp_number_service.get_whatsapp_numbers(
        db=db,
        skip=skip,
        limit=limit,
        organization_id=filter_org_id,
        is_active=is_active,
        search=search
    )
    return WhatsAppNumberListResponse(items=whatsapp_numbers, total=total)


@router.get("/{whatsapp_number_id}", response_model=WhatsAppNumberResponse)
def get_whatsapp_number(
    whatsapp_number_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get WhatsApp number by ID"""
    whatsapp_number = whatsapp_number_service.get_whatsapp_number(db, whatsapp_number_id)
    if not whatsapp_number:
        raise HTTPException(status_code=404, detail="WhatsApp number not found")
    
    # Check permissions (non-super admins can only see their organization's numbers)
    is_super_admin = False
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
    
    if not is_super_admin and hasattr(current_user, 'role') and current_user.role:
        role_str = str(current_user.role).upper()
        if role_str in ["SUPER_ADMIN", "ADMIN"]:
            is_super_admin = True
    
    if not is_super_admin:
        if current_user.organization_id != whatsapp_number.organization_id:
            raise HTTPException(status_code=403, detail="You don't have permission to access this WhatsApp number")
    
    return whatsapp_number


@router.patch("/{whatsapp_number_id}", response_model=WhatsAppNumberResponse)
def update_whatsapp_number(
    whatsapp_number_id: UUID,
    whatsapp_number_data: WhatsAppNumberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update a WhatsApp number (Admin only)"""
    try:
        whatsapp_number = whatsapp_number_service.update_whatsapp_number(
            db, whatsapp_number_id, whatsapp_number_data
        )
        if not whatsapp_number:
            raise HTTPException(status_code=404, detail="WhatsApp number not found")
        return whatsapp_number
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update WhatsApp number: {str(e)}")


@router.delete("/{whatsapp_number_id}", status_code=204)
def delete_whatsapp_number(
    whatsapp_number_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete a WhatsApp number (Admin only)"""
    success = whatsapp_number_service.delete_whatsapp_number(db, whatsapp_number_id)
    if not success:
        raise HTTPException(status_code=404, detail="WhatsApp number not found")

