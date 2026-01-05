from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID

from schemas.customer_schema import CustomerOut
from schemas.user_schema import UserCreate, UserRead, UserUpdate
from models.models import User, Customer
from services import crud
from auth import get_current_user, get_current_admin_user
from database.db import get_db
from services.customer_service import get_customers_for_user
from utils.organization_filter import get_user_organization_id

router = APIRouter(
    tags=["users"]
)

@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Get the current user's details based on the token"""
    return current_user

@router.post("/", response_model=UserRead)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)  # Only admins can create users
):
    if crud.get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Determine current user's role
    is_super_admin = False
    is_org_admin = False
    
    # Check new role system first (role_obj)
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
        elif current_user.role_obj.name == "ORG_ADMIN":
            is_org_admin = True
    
    # Also check legacy role enum for backward compatibility
    if not is_super_admin and not is_org_admin and hasattr(current_user, 'role') and current_user.role:
        role_str = str(current_user.role).upper()
        if role_str == "SUPER_ADMIN":
            is_super_admin = True
        elif role_str in ["ADMIN", "ORG_ADMIN"]:
            is_org_admin = True
    
    # Determine the role being created
    creating_role = None
    if user.role_id:
        from models.models import Role
        role_obj = db.query(Role).filter(Role.id == user.role_id).first()
        if role_obj:
            creating_role = role_obj.name
    elif user.role:
        creating_role = user.role.value if hasattr(user.role, 'value') else str(user.role).upper()
    
    # Role-based permission checks
    if is_org_admin:
        # Org Admin can only create ORG_ADMIN and AGENT
        if creating_role == "SUPER_ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization Admins cannot create Super Admin users"
            )
        if creating_role not in ["ORG_ADMIN", "AGENT"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Organization Admins can only create Organization Admin and Agent users, not {creating_role}"
            )
        
        # Org Admin can only create users in their own organization
        if user.organization_id and user.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization Admins can only create users in their own organization"
            )
        
        # Auto-set organization_id to current user's organization if not provided
        if not user.organization_id:
            if not current_user.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current user's organization_id is not set"
                )
            user.organization_id = current_user.organization_id
            print(f"[create_user] Org Admin auto-setting organization_id to {user.organization_id}")
    
    elif is_super_admin:
        # Super Admin can create SUPER_ADMIN, ORG_ADMIN, and AGENT (any organization)
        if creating_role not in ["SUPER_ADMIN", "ORG_ADMIN", "AGENT"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid role: {creating_role}"
            )
    else:
        # This should not happen as get_current_admin_user ensures admin access
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users"
        )

    try:
        # create_user now handles organization_id and role_id validation
        # It ensures:
        # - SUPER_ADMIN has organization_id = None
        # - ORG_ADMIN and AGENT have organization_id set
        # - Organization exists if organization_id is provided
        created_user = crud.create_user(db, user)
        print(f"[create_user] User created successfully: {created_user.email}, role: {creating_role}, org_id: {created_user.organization_id}")
        return created_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

@router.get("/")
def read_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by username, email, or name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),  # Only admins can list all users
):
    """
    List users with pagination and optional search.
    Super Admins see all users, Org Admins see only users from their organization.
    """
    organization_id = get_user_organization_id(current_user)
    # Debug logging
    print(f"[read_users] Current user: {current_user.email}, role: {current_user.role}, role_obj: {current_user.role_obj.name if current_user.role_obj else None}")
    print(f"[read_users] Organization ID filter: {organization_id}")
    result = crud.get_users(db, skip=skip, limit=limit, search=search, organization_id=organization_id)
    print(f"[read_users] Returning {len(result.get('items', []))} users out of {result.get('total', 0)} total")
    return result

@router.get("/{user_id}", response_model=UserRead)
def read_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)  # Only admins can view other users
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    user: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # Allow users to update their own profile
):
    # Get the user being updated
    target_user = crud.get_user(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # If current user is an agent, they can only update their own profile
    if current_user.role == "AGENT":
        if current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Agents can only update their own profile"
            )
        # Agents cannot change their role
        if user.role is not None and user.role != target_user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Agents cannot change their role"
            )
        # Remove role from update if agent is trying to update themselves
        user.role = None
    
    # Only admins and super admins can update other users' roles
    # Check new role system first (role_obj)
    is_admin = False
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name in ["SUPER_ADMIN", "ORG_ADMIN"]:
            is_admin = True
    
    # Also check legacy role enum for backward compatibility
    if not is_admin and hasattr(current_user, 'role') and current_user.role:
        if str(current_user.role).upper() in ["ADMIN", "SUPER_ADMIN"]:
            is_admin = True
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update other users"
        )
    
    try:
        # update_user now handles organization_id and role_id validation
        # It ensures:
        # - SUPER_ADMIN has organization_id = None
        # - ORG_ADMIN and AGENT have organization_id set
        # - Organization exists if organization_id is provided
        updated = crud.update_user(db, user_id, user)
        if not updated:
            raise HTTPException(status_code=404, detail="User not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")

@router.delete("/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)  # Only admins can delete users
):
    deleted = crud.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}

@router.get("/{user_id}/customers")
def get_user_customers(
    user_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by name, phone, or email"),
    db: Session = Depends(get_db)
):
    """Get customers assigned to a user with pagination and optional search."""
    return get_customers_for_user(db, user_id, skip=skip, limit=limit, search=search)


@router.get("/role/{role}")
def get_users_by_role(
        role: str,
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=200, description="Max records to return"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_admin_user)  # Only admins can filter by role
):
    """Get users by role with pagination."""
    query = db.query(User).filter(User.role == role.upper())
    total = query.count()
    users = query.offset(skip).limit(limit).all()
    return {"items": users, "total": total, "skip": skip, "limit": limit}
