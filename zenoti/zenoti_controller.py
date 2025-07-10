from fastapi import APIRouter, Query, Depends, HTTPException

from zenoti.zenoti_schema import CenterNamesResponse
from zenoti.zenoti_service import get_guest_details, fetch_center_names
from auth import get_current_user  # Or from auth.auth if needed
from models.models import User

router = APIRouter(tags=["Zenoti"])

@router.get("/guest")
async def fetch_guest(
    phone: str = Query(..., example="9739117228"),
    current_user: User = Depends(get_current_user)  # Keep for auth
):
    return await get_guest_details(phone)

@router.get("/center-names", response_model=CenterNamesResponse)
def get_center_names():
    try:
        centers = fetch_center_names()
        return {"centers": centers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

