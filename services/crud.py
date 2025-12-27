from sqlalchemy.orm import Session
from models.models import User
from schemas.user_schema import UserCreate, UserUpdate
import uuid

from utils.utils import get_password_hash


def get_user(db: Session, user_id: uuid.UUID):
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 50, search: str = None):
    """Get all users with pagination and optional search."""
    query = db.query(User)

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (User.username.ilike(search_term)) |
            (User.email.ilike(search_term)) |
            (User.first_name.ilike(search_term)) |
            (User.last_name.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    users = query.offset(skip).limit(limit).all()

    return {"items": users, "total": total, "skip": skip, "limit": limit}


def create_user(db: Session, user: UserCreate):
    # SUPER_ADMIN should not have an organization_id (it's nullable by default)
    # For other roles, organization_id can be set separately if needed
    db_user = User(
        username=user.username,
        password=get_password_hash(user.password),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone_number=user.phone_number,
        role=user.role
        # organization_id is None by default, which is correct for SUPER_ADMIN
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user



def update_user(db: Session, user_id: uuid.UUID, user: UserUpdate):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return None
    for field, value in user.dict(exclude_unset=True).items():
        setattr(db_user, field, value)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: uuid.UUID):
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user
