from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime

router = APIRouter(prefix="/api", tags=["click-tracking"])

class ClickTrackingData(BaseModel):
    campaign: str
    content: str
    center_name: str
    location: str
    timestamp: str
    user_agent: Optional[str] = None
    referrer: Optional[str] = None

@router.post("/track-click")
async def track_click(click_data: ClickTrackingData, db: Session = Depends(get_db)):
    """Track website clicks for analytics"""
    try:
        # Log the click data
        print(f"Click tracked: {click_data.center_name} - {click_data.campaign}")
        print(f"User Agent: {click_data.user_agent}")
        print(f"Referrer: {click_data.referrer}")
        
        # You can store this in a database table if needed
        # For now, just log it
        
        return {
            "status": "success",
            "message": "Click tracked successfully",
            "data": {
                "center": click_data.center_name,
                "campaign": click_data.campaign,
                "timestamp": click_data.timestamp
            }
        }
    except Exception as e:
        print(f"Error tracking click: {e}")
        raise HTTPException(status_code=500, detail="Failed to track click")

@router.get("/tracking-stats")
async def get_tracking_stats(db: Session = Depends(get_db)):
    """Get basic tracking statistics"""
    return {
        "status": "success",
        "message": "Tracking is active",
        "timestamp": datetime.now().isoformat()
    }
