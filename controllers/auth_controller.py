from datetime import timedelta, datetime
from http.client import HTTPException
from pydantic import BaseModel
from database.db import get_db
from services.crud import get_user_by_username, get_user_by_email
from utils.email import send_forgot_password_email
from fastapi import APIRouter, HTTPException, Depends
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from auth import pwd_context, SECRET_KEY, ALGORITHM
from models.models import User
from schemas.ResetPasswordSchema import ResetPasswordRequest
router = APIRouter()

class ForgotPasswordRequest(BaseModel):
    identifier: str  # could be username or email



@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Try email or username
    user = get_user_by_email(db, req.identifier) or get_user_by_username(db, req.identifier)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Generate JWT token
    token_data = {
        "sub": str(user.id),
        "exp": datetime.utcnow() + timedelta(minutes=30)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    reset_link = f"https://localhost:5173/reset-password?token={token}"

    try:
        send_forgot_password_email(user.email, reset_link)
        return {"message": "Password reset link sent to the user's email"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        decoded = jwt.decode(payload.token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = pwd_context.hash(payload.new_password)
    db.commit()
    return {"message": "Password has been reset successfully"}