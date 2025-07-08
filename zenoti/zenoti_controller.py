from fastapi import APIRouter, Query, Depends
from .zenoti_service import get_guest_details
from auth import get_current_user
from models.models import User
router = APIRouter(prefix="/zenoti", tags=["Zenoti"])

@router.get("/guest")
async def fetch_guest(phone: str = Query(..., example="9739117228"), current_user: User = Depends(get_current_user)):
    return await get_guest_details(phone)
