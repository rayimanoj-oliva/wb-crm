from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database.db import SessionLocal, get_db
from service.crud import get_user_by_username
from models.models import User
from utils.utils import verify_password

# -- Secret Key & Config --
SECRET_KEY = "e6a8b7eb54d526ff59363d3b6eccfc254d4041674cd50d69b67a602f9490cb9e8c2bc4c2e15f2f31e28d229cd5a823b4ba212f8f6372ecf70c9a15fa82e9e3d509110adeed7a12c0cbe61dc591390acc8fd8ec0faad7c1e0134f6c73bf8b32346b85844bc84bd186af00ee11ce29fb3d34d2681621c41c210bea6167535d307a24deb2de5f1aca2a3b42d4df94755639fe7d6d870b795cd00025d98a5a2f311caf36f90d244d99b4fcd871ed6eced7f72caf04ae4d08327584d8f073b726d8ef400b477a3dca67602eef67aa7e554a106f095e378c868b766b489137f4a0e495a2ccc81827f863fd7a7e5bd0a1e9bd70623b2edffb09d05df84ca69760b4c457"  # use a .env file in real apps
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user