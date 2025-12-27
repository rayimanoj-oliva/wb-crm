from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload
from database.db import get_db
from services.crud import get_user_by_username
from models.models import User
from utils.utils import verify_password

import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

# -- Hashing --
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")



# -- Token helpers --
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -- Auth logic --
def authenticate_user(db: Session, username: str, password: str):
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.password):
        return None
    return user


# -- Get current user from token --

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).options(
        joinedload(User.role_obj),
        joinedload(User.organization)
    ).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


# -- Role-based access control --
def get_current_admin_user(current_user: User = Depends(get_current_user)):
    """Dependency to ensure the current user is an ADMIN or SUPER_ADMIN"""
    # Check new role system first
    is_admin = False
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name in ["SUPER_ADMIN", "ORG_ADMIN"]:
            is_admin = True
    # Fallback to legacy role enum
    elif current_user.role in ["ADMIN", "SUPER_ADMIN"]:
        is_admin = True
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def get_current_agent_user(current_user: User = Depends(get_current_user)):
    """Dependency to ensure the current user is an AGENT"""
    if current_user.role != "AGENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent access required"
        )
    return current_user


def get_current_super_admin(current_user: User = Depends(get_current_user)):
    """Dependency to ensure the current user is a SUPER_ADMIN"""
    is_super_admin = False
    # Check new role system first
    if hasattr(current_user, 'role_obj') and current_user.role_obj:
        if current_user.role_obj.name == "SUPER_ADMIN":
            is_super_admin = True
    # Fallback to legacy role enum
    elif current_user.role == "ADMIN":
        is_super_admin = True
    
    if not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required"
        )
    return current_user