from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from schemas.customer_schema import CustomerOut
from schemas.user_schema import UserCreate, UserRead, UserUpdate
from models.models import User, Customer
from services import crud
from auth import get_current_user
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
    # current_user: User = Depends(get_current_user)  # Authenticated user
):
    if crud.get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # # Optional: only admins can assign the ADMIN role
    # if user.role == "ADMIN" and current_user.role != "ADMIN":
    #     raise HTTPException(status_code=403, detail="Only admins can create admin users")

    return crud.create_user(db, user)

@router.get("/", response_model=list[UserRead])
def read_users(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_users(db, skip=skip, limit=limit)

@router.get("/{user_id}", response_model=UserRead)
def read_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
):
    updated = crud.update_user(db, user_id, user)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated

@router.delete("/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deleted = crud.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}

@router.get("/{user_id}/customers", response_model=List[CustomerOut])
def get_user_customers(user_id: UUID, db: Session = Depends(get_db)):
    return get_customers_for_user(db, user_id)


@router.get("/role/{role}", response_model=list[UserRead])
def get_users_by_role(
        role: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admins only")

    return db.query(User).filter(User.role == role.upper()).all()
