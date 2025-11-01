"""
Debug endpoint to check follow-up status
Useful for troubleshooting in production
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from database.db import get_db
from models.models import Customer
from services.followup_service import due_customers_for_followup

router = APIRouter()

@router.get("/debug/followup-status")
async def debug_followup_status(db: Session = Depends(get_db)):
    """Debug endpoint to check follow-up status"""
    now = datetime.utcnow()
    
    # Get all scheduled
    all_scheduled = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None)
    ).all()
    
    # Get due customers
    due_customers = due_customers_for_followup(db)
    
    # Get examples
    examples = []
    for c in all_scheduled[:5]:
        time_diff = (c.next_followup_time - now).total_seconds() if c.next_followup_time else None
        examples.append({
            "wa_id": c.wa_id,
            "name": c.name,
            "next_followup_time": c.next_followup_time.isoformat() if c.next_followup_time else None,
            "last_message_type": c.last_message_type,
            "last_interaction_time": c.last_interaction_time.isoformat() if c.last_interaction_time else None,
            "minutes_until_due": int(time_diff / 60) if time_diff else None,
            "is_due": time_diff and time_diff <= 0
        })
    
    return {
        "current_utc_time": now.isoformat(),
        "total_scheduled": len(all_scheduled),
        "total_due": len(due_customers),
        "examples": examples,
        "due_customers": [
            {
                "wa_id": c.wa_id,
                "name": c.name,
                "next_followup_time": c.next_followup_time.isoformat() if c.next_followup_time else None,
                "last_message_type": c.last_message_type
            }
            for c in due_customers
        ]
    }

@router.post("/debug/test-followup/{wa_id}")
async def test_followup_for_customer(wa_id: str, db: Session = Depends(get_db)):
    """Manually trigger follow-up for a specific customer (for testing)"""
    from services.followup_service import send_followup1_interactive
    from services.customer_service import get_customer_record_by_wa_id
    
    customer = get_customer_record_by_wa_id(db, wa_id)
    if not customer:
        return {"error": f"Customer with wa_id {wa_id} not found"}
    
    try:
        await send_followup1_interactive(db, wa_id=wa_id)
        return {"success": True, "message": f"Follow-Up 1 sent to {wa_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

