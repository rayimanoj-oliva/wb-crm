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

    return crud.create_user(db, user)

@router.get("/")
def read_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by username, email, or name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),  # Only admins can list all users
):
    """List users with pagination and optional search."""
    return crud.get_users(db, skip=skip, limit=limit, search=search)

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
    
    # Only admins can update other users' roles
    elif current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update other users"
        )
    
    updated = crud.update_user(db, user_id, user)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated

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
