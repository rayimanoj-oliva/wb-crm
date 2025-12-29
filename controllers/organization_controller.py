"""
Organization controller for API endpoints
"""
from typing import Optional
from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import csv
import io

from database.db import get_db
from models.models import User
from schemas.organization_schema import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationListResponse
)
from services import organization_service
from auth import get_current_user, get_current_super_admin

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("/", response_model=OrganizationResponse, status_code=201)
def create_organization(
    organization_data: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin)
):
    """Create a new organization (Super Admin only)"""
    try:
        organization = organization_service.create_organization(
            db, organization_data, current_user
        )
        return organization
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create organization: {str(e)}")


@router.get("/", response_model=OrganizationListResponse)
def list_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    from_date: Optional[date] = Query(None, description="Filter by created date from"),
    to_date: Optional[date] = Query(None, description="Filter by created date to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List organizations (filtered by user role)"""
    organizations, total = organization_service.get_organizations(
        db=db,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        from_date=from_date,
        to_date=to_date,
        current_user=current_user
    )
    return OrganizationListResponse(items=organizations, total=total)


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get organization by ID"""
    organization = organization_service.get_organization(db, organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check permissions
    is_super_admin = False
    if current_user.role_obj and current_user.role_obj.name == "SUPER_ADMIN":
        is_super_admin = True
    elif current_user.role == "ADMIN":  # Legacy support
        is_super_admin = True
    
    if not is_super_admin:
        # Non-super admins can only see their own organization
        if current_user.organization_id != organization_id:
            raise HTTPException(status_code=403, detail="You don't have permission to access this organization")
    
    return organization


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: UUID,
    organization_data: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an organization (Super Admin or Org Admin of that org)"""
    try:
        organization = organization_service.update_organization(
            db, organization_id, organization_data, current_user
        )
        if not organization:
            raise HTTPException(status_code=404, detail="Organization not found")
        return organization
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update organization: {str(e)}")


@router.delete("/{organization_id}", status_code=204)
def delete_organization(
    organization_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin)
):
    """Delete an organization (Super Admin only)"""
    success = organization_service.delete_organization(db, organization_id, current_user)
    if not success:
        raise HTTPException(status_code=404, detail="Organization not found")


@router.get("/export/csv")
def export_organizations_csv(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin)
):
    """Export organizations to CSV (Super Admin only)"""
    # Get all organizations (no pagination for export)
    organizations, _ = organization_service.get_organizations(
        db=db,
        skip=0,
        limit=10000,  # Large limit for export
        search=search,
        is_active=is_active,
        from_date=from_date,
        to_date=to_date,
        current_user=current_user
    )
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Name', 'Code', 'Slug', 'Description', 'Status', 
        'Created Date', 'Last Modified'
    ])
    
    # Write data
    for org in organizations:
        writer.writerow([
            org.name,
            org.code or '',
            org.slug or '',
            org.description or '',
            'Active' if org.is_active else 'Inactive',
            org.created_at.strftime('%Y-%m-%d %H:%M:%S') if org.created_at else '',
            org.updated_at.strftime('%Y-%m-%d %H:%M:%S') if org.updated_at else ''
        ])
    
    # Prepare response
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=organizations_export.csv"
        }
    )

