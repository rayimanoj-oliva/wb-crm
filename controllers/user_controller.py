
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from schemas.UserSchema import UserCreate, UserRead, UserUpdate
from models.models import User
from services import crud
from auth import get_current_user
from database.db import get_db

router = APIRouter()

@router.post("/users/", response_model=UserRead)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, user)

@router.get("/users/", response_model=list[UserRead])
def read_users(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_users(db, skip=skip, limit=limit)

@router.get("/users/{user_id}", response_model=UserRead)
def read_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/users/{user_id}", response_model=UserRead)
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

@router.delete("/users/{user_id}")
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deleted = crud.delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}