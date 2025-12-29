"""
Role controller for API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.db import get_db
from models.models import Role, User
from auth import get_current_user, get_current_admin_user

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("/")
def list_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all available roles (for dropdowns in user creation)"""
    query = db.query(Role)
    
    if is_active is not None:
        query = query.filter(Role.is_active == is_active)
    else:
        # By default, only return active roles
        query = query.filter(Role.is_active == True)
    
    total = query.count()
    roles = query.order_by(Role.name).offset(skip).limit(limit).all()
    
    return {
        "items": roles,
        "total": total
    }


@router.get("/{role_id}")
def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get role by ID"""
    from uuid import UUID as UUIDType
    
    try:
        role_uuid = UUIDType(role_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid role ID format")
    
    role = db.query(Role).filter(Role.id == role_uuid).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role

