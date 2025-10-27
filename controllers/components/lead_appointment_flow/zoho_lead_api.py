"""
API Endpoints for Zoho Lead Retrieval
REST API endpoints to get leads created through WhatsApp source
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from controllers.components.lead_appointment_flow.zoho_lead_retrieval import (
    get_whatsapp_leads,
    get_lead_by_id,
    get_lead_statistics
)

# Create router for lead retrieval endpoints
router = APIRouter(prefix="/api/zoho-leads", tags=["Zoho Leads"])


# Pydantic models for request/response
class LeadResponse(BaseModel):
    success: bool
    leads: Optional[list] = None
    total_count: Optional[int] = None
    page_info: Optional[dict] = None
    query_info: Optional[dict] = None
    error: Optional[str] = None


class LeadDetailResponse(BaseModel):
    success: bool
    lead: Optional[dict] = None
    raw_data: Optional[dict] = None
    error: Optional[str] = None


class StatisticsResponse(BaseModel):
    success: bool
    statistics: Optional[dict] = None
    leads: Optional[list] = None
    error: Optional[str] = None


# API Endpoints

@router.get("/whatsapp", response_model=LeadResponse)
async def get_whatsapp_source_leads(
    limit: int = Query(200, description="Number of records to return (max 200)", le=200),
    page: int = Query(1, description="Page number for pagination", ge=1),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    sort_by: str = Query("Created_Time", description="Field to sort by"),
    date_from: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    date_to: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    lead_status: Optional[str] = Query(None, description="Filter by lead status")
):
    """
    Get leads created through WhatsApp Lead-to-Appointment Flow
    
    - **limit**: Number of records to return (max 200)
    - **page**: Page number for pagination
    - **sort_order**: Sort order ('asc' or 'desc')
    - **sort_by**: Field to sort by (e.g., 'Created_Time', 'Modified_Time')
    - **date_from**: Start date in YYYY-MM-DD format
    - **date_to**: End date in YYYY-MM-DD format
    - **lead_status**: Filter by lead status (CALL_INITIATED, PENDING, NO_CALLBACK)
    """
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=page,
            sort_order=sort_order,
            sort_by=sort_by,
            date_from=date_from,
            date_to=date_to,
            lead_status=lead_status
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info=result["query_info"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{lead_id}", response_model=LeadDetailResponse)
async def get_specific_lead(
    lead_id: str = Path(..., description="Zoho CRM Lead ID")
):
    """
    Get a specific lead by ID
    
    - **lead_id**: Zoho CRM Lead ID
    """
    
    try:
        result = await get_lead_by_id(lead_id)
        
        if result["success"]:
            return LeadDetailResponse(
                success=True,
                lead=result["lead"],
                raw_data=result["raw_data"]
            )
        else:
            raise HTTPException(status_code=404, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/statistics/summary", response_model=StatisticsResponse)
async def get_lead_statistics(
    days: int = Query(30, description="Number of days to analyze", ge=1, le=365)
):
    """
    Get statistics for WhatsApp leads over a specified period
    
    - **days**: Number of days to analyze (1-365)
    """
    
    try:
        result = await get_lead_statistics(days)
        
        if result["success"]:
            return StatisticsResponse(
                success=True,
                statistics=result["statistics"],
                leads=result["leads"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Additional convenience endpoints

@router.get("/whatsapp/recent", response_model=LeadResponse)
async def get_recent_whatsapp_leads(
    limit: int = Query(20, description="Number of recent leads to return", le=200),
    hours: int = Query(24, description="Number of hours to look back", ge=1, le=168)
):
    """
    Get recent WhatsApp source leads from the last few hours
    
    - **limit**: Number of recent leads to return (max 200)
    - **hours**: Number of hours to look back (1-168 hours = 1 week max)
    """
    
    from datetime import datetime, timedelta
    
    # Calculate date range
    date_from = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d")
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=1,
            sort_order="desc",
            sort_by="Created_Time",
            date_from=date_from
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info={
                    **result["query_info"],
                    "hours_back": hours,
                    "date_from": date_from
                }
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/whatsapp/today", response_model=LeadResponse)
async def get_todays_whatsapp_leads(
    limit: int = Query(50, description="Number of leads to return", le=200)
):
    """
    Get today's WhatsApp source leads
    
    - **limit**: Number of leads to return (max 200)
    """
    
    from datetime import datetime
    
    date_from = datetime.now().strftime("%Y-%m-%d")
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=1,
            sort_order="desc",
            sort_by="Created_Time",
            date_from=date_from
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info={
                    **result["query_info"],
                    "period": "today",
                    "date_from": date_from
                }
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/whatsapp/this-week", response_model=LeadResponse)
async def get_this_weeks_whatsapp_leads(
    limit: int = Query(100, description="Number of leads to return", le=200)
):
    """
    Get this week's WhatsApp source leads
    
    - **limit**: Number of leads to return (max 200)
    """
    
    from datetime import datetime, timedelta
    
    # Get start of current week (Monday)
    today = datetime.now()
    days_since_monday = today.weekday()
    start_of_week = today - timedelta(days=days_since_monday)
    date_from = start_of_week.strftime("%Y-%m-%d")
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=1,
            sort_order="desc",
            sort_by="Created_Time",
            date_from=date_from
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info={
                    **result["query_info"],
                    "period": "this_week",
                    "date_from": date_from
                }
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/whatsapp/latest", response_model=LeadResponse)
async def get_latest_whatsapp_leads(
    limit: int = Query(10, description="Number of latest leads to return", le=50)
):
    """
    Get the latest WhatsApp source leads (most recent first)
    
    - **limit**: Number of latest leads to return (max 50)
    """
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=1,
            sort_order="desc",
            sort_by="Created_Time"
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info={
                    **result["query_info"],
                    "period": "latest",
                    "description": "Most recent leads first"
                }
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/whatsapp/q5-events", response_model=LeadResponse)
async def get_q5_events(
    limit: int = Query(200, description="Number of records to return", le=200),
    page: int = Query(1, description="Page number for pagination", ge=1),
    days: int = Query(30, description="Number of days to look back", ge=1, le=365)
):
    """
    Get Q5 events (leads where user requested callback)
    
    - **limit**: Number of records to return
    - **page**: Page number for pagination
    - **days**: Number of days to look back
    """
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=page,
            lead_status="CALL_INITIATED",
            date_from=date_from
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info=result["query_info"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/whatsapp/termination-events", response_model=LeadResponse)
async def get_termination_events(
    limit: int = Query(200, description="Number of records to return", le=200),
    page: int = Query(1, description="Page number for pagination", ge=1),
    days: int = Query(30, description="Number of days to look back", ge=1, le=365)
):
    """
    Get termination events (leads for follow-up/remarketing)
    
    - **limit**: Number of records to return
    - **page**: Page number for pagination
    - **days**: Number of days to look back
    """
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=page,
            lead_status="NO_CALLBACK",
            date_from=date_from
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info=result["query_info"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/whatsapp/pending", response_model=LeadResponse)
async def get_pending_leads(
    limit: int = Query(200, description="Number of records to return", le=200),
    page: int = Query(1, description="Page number for pagination", ge=1),
    days: int = Query(30, description="Number of days to look back", ge=1, le=365)
):
    """
    Get pending leads (completed flow but no callback requested)
    
    - **limit**: Number of records to return
    - **page**: Page number for pagination
    - **days**: Number of days to look back
    """
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        result = await get_whatsapp_leads(
            limit=limit,
            page=page,
            lead_status="PENDING",
            date_from=date_from
        )
        
        if result["success"]:
            return LeadResponse(
                success=True,
                leads=result["leads"],
                total_count=result["total_count"],
                page_info=result["page_info"],
                query_info=result["query_info"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check for Zoho lead retrieval service"""
    return {
        "status": "healthy",
        "service": "Zoho Lead Retrieval API",
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            "/api/zoho-leads/whatsapp",
            "/api/zoho-leads/{lead_id}",
            "/api/zoho-leads/statistics/summary",
            "/api/zoho-leads/whatsapp/recent",
            "/api/zoho-leads/whatsapp/today",
            "/api/zoho-leads/whatsapp/this-week",
            "/api/zoho-leads/whatsapp/latest",
            "/api/zoho-leads/whatsapp/q5-events",
            "/api/zoho-leads/whatsapp/termination-events",
            "/api/zoho-leads/whatsapp/pending"
        ]
    }
