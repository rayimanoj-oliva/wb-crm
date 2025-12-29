"""
Organization service for business logic
"""
from typing import Optional, List
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, and_
from uuid import UUID

from models.models import Organization, User, Role
from schemas.organization_schema import OrganizationCreate, OrganizationUpdate


def create_organization(db: Session, organization_data: OrganizationCreate, created_by_user: User) -> Organization:
    """Create a new organization"""
    # Generate slug if not provided
    slug = organization_data.slug
    if not slug and organization_data.name:
        slug = organization_data.name.lower().replace(" ", "-").replace("_", "-")
        # Remove special characters
        slug = "".join(c if c.isalnum() or c == "-" else "" for c in slug)
    
    # Check if slug already exists
    if slug:
        existing = db.query(Organization).filter(Organization.slug == slug).first()
        if existing:
            raise ValueError(f"Organization with slug '{slug}' already exists")
    
    # Check if code already exists
    code = organization_data.code
    if code:
        existing_code = db.query(Organization).filter(Organization.code == code).first()
        if existing_code:
            raise ValueError(f"Organization with code '{code}' already exists")
    
    organization = Organization(
        name=organization_data.name,
        code=code,
        slug=slug,
        description=organization_data.description,
        is_active=organization_data.is_active
    )
    
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def get_organization(db: Session, organization_id: UUID) -> Optional[Organization]:
    """Get organization by ID"""
    return db.query(Organization).filter(Organization.id == organization_id).first()


def get_organizations(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: Optional[User] = None
) -> tuple[List[Organization], int]:
    """Get list of organizations with filtering"""
    query = db.query(Organization)
    
    # Filter by user's role
    if current_user:
        # Check if user has SUPER_ADMIN role
        is_super_admin = False
        
        # Check new role system first
        if hasattr(current_user, 'role_obj') and current_user.role_obj:
            if current_user.role_obj.name == "SUPER_ADMIN":
                is_super_admin = True
        
        # Also check legacy role enum (check both independently for better compatibility)
        if not is_super_admin and hasattr(current_user, 'role') and current_user.role:
            role_str = str(current_user.role).upper()
            if role_str in ["SUPER_ADMIN", "ADMIN"]:
                is_super_admin = True
        
        if not is_super_admin:
            # Non-super admins can only see their own organization
            if current_user.organization_id:
                query = query.filter(Organization.id == current_user.organization_id)
            else:
                # User has no organization, return empty
                return [], 0
    
    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Organization.name.ilike(search_pattern),
                Organization.code.ilike(search_pattern),
                Organization.slug.ilike(search_pattern),
                Organization.description.ilike(search_pattern)
            )
        )
    
    if is_active is not None:
        query = query.filter(Organization.is_active == is_active)
    
    # Date filtering
    if from_date:
        query = query.filter(func.date(Organization.created_at) >= from_date)
    if to_date:
        query = query.filter(func.date(Organization.created_at) <= to_date)
    
    # Order by created_at descending (newest first)
    query = query.order_by(Organization.created_at.desc())
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    organizations = query.offset(skip).limit(limit).all()
    
    return organizations, total


def update_organization(
    db: Session,
    organization_id: UUID,
    organization_data: OrganizationUpdate,
    current_user: User
) -> Optional[Organization]:
    """Update an organization"""
    organization = get_organization(db, organization_id)
    if not organization:
        return None
    
    # Check permissions
    is_super_admin = False
    
    # Check new role system first
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
    
    # Also check legacy role enum (check both independently for better compatibility)
    if not is_super_admin and hasattr(current_user, 'role') and current_user.role:
        role_str = str(current_user.role).upper()
        if role_str in ["SUPER_ADMIN", "ADMIN"]:
            is_super_admin = True
    
    if not is_super_admin:
        # Non-super admins can only update their own organization
        if current_user.organization_id != organization_id:
            raise PermissionError("You don't have permission to update this organization")
    
    # Update fields
    update_data = organization_data.model_dump(exclude_unset=True)
    
    # Handle slug uniqueness check
    if "slug" in update_data and update_data["slug"]:
        existing = db.query(Organization).filter(
            Organization.slug == update_data["slug"],
            Organization.id != organization_id
        ).first()
        if existing:
            raise ValueError(f"Organization with slug '{update_data['slug']}' already exists")
    
    # Handle code uniqueness check
    if "code" in update_data and update_data["code"]:
        existing_code = db.query(Organization).filter(
            Organization.code == update_data["code"],
            Organization.id != organization_id
        ).first()
        if existing_code:
            raise ValueError(f"Organization with code '{update_data['code']}' already exists")
    
    for field, value in update_data.items():
        setattr(organization, field, value)
    
    db.commit()
    db.refresh(organization)
    return organization


def delete_organization(db: Session, organization_id: UUID, current_user: User) -> bool:
    """Delete an organization (soft delete by setting is_active=False)"""
    organization = get_organization(db, organization_id)
    if not organization:
        return False
    
    # Only Super Admin can delete organizations
    is_super_admin = False
    
    # Check new role system first
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
    
    # Also check legacy role enum (check both independently for better compatibility)
    if not is_super_admin and hasattr(current_user, 'role') and current_user.role:
        role_str = str(current_user.role).upper()
        if role_str in ["SUPER_ADMIN", "ADMIN"]:
            is_super_admin = True
    
    if not is_super_admin:
        raise PermissionError("Only Super Admin can delete organizations")
    
    # Soft delete
    organization.is_active = False
    db.commit()
    return True

