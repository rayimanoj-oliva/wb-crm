from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional

from database.db import get_db
from models.models import Customer, Message
from services.followup_service import due_customers_for_followup

router = APIRouter()


@router.get("/status")
def check_followup_status(db: Session = Depends(get_db)):
    """Diagnostic endpoint to check if follow-up scheduler is working"""
    now = datetime.utcnow()
    
    # Check customers due for follow-up
    due_customers = due_customers_for_followup(db)
    due_customers_count = len(due_customers)
    
    # Count customers with scheduled follow-ups
    scheduled_count = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None)
    ).count()
    
    # Get upcoming follow-ups in next hour
    next_hour = now + timedelta(hours=1)
    upcoming_count = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None),
        Customer.next_followup_time > now,
        Customer.next_followup_time <= next_hour
    ).count()
    
    # Get recent follow-up messages sent in last 24 hours
    yesterday = now - timedelta(hours=24)
    recent_followups = db.query(Message).filter(
        Message.body.contains("Follow-Up"),
        Message.timestamp >= yesterday
    ).order_by(Message.timestamp.desc()).limit(10).all()
    
    # Get customers with follow-up states
    followup1_sent = db.query(Customer).filter(
        Customer.last_message_type.ilike("%follow_up_1_sent%")
    ).count()
    
    followup2_sent = db.query(Customer).filter(
        Customer.last_message_type.ilike("%follow_up_2_sent%")
    ).count()
    
    # Check if there are any scheduled follow-ups in the past (stuck)
    stuck_count = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None),
        Customer.next_followup_time < now - timedelta(minutes=10)
    ).count()
    
    return {
        "status": "active",
        "timestamp": now.isoformat(),
        "scheduler_status": {
            "due_customers_now": due_customers_count,
            "scheduled_followups": scheduled_count,
            "upcoming_in_next_hour": upcoming_count,
            "stuck_followups_old": stuck_count,
        },
        "customer_states": {
            "followup1_sent": followup1_sent,
            "followup2_sent": followup2_sent,
        },
        "recent_activity": {
            "followups_sent_last_24h": len(recent_followups),
            "latest_followups": [
                {
                    "message_id": msg.message_id,
                    "body": msg.body,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "wa_id": msg.to_wa_id
                }
                for msg in recent_followups[:5]
            ]
        },
        "due_customers_detail": [
            {
                "customer_id": c.id,
                "wa_id": c.wa_id,
                "last_message_type": c.last_message_type,
                "next_followup_time": c.next_followup_time.isoformat() if c.next_followup_time else None,
                "last_interaction_time": c.last_interaction_time.isoformat() if c.last_interaction_time else None,
                "overdue_minutes": int((now - c.next_followup_time).total_seconds() / 60) if c.next_followup_time and c.next_followup_time < now else 0
            }
            for c in due_customers[:10]  # Limit to 10 for response size
        ]
    }


@router.get("/due")
def get_due_customers(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get list of customers currently due for follow-up"""
    due_customers = due_customers_for_followup(db)
    
    return {
        "count": len(due_customers),
        "customers": [
            {
                "customer_id": c.id,
                "wa_id": c.wa_id,
                "name": c.name,
                "last_message_type": c.last_message_type,
                "next_followup_time": c.next_followup_time.isoformat() if c.next_followup_time else None,
                "last_interaction_time": c.last_interaction_time.isoformat() if c.last_interaction_time else None,
            }
            for c in due_customers[:limit]
        ]
    }


@router.get("/scheduled")
def get_scheduled_followups(
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get all scheduled follow-ups within the next N hours"""
    now = datetime.utcnow()
    future_time = now + timedelta(hours=hours)
    
    scheduled = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None),
        Customer.next_followup_time > now,
        Customer.next_followup_time <= future_time
    ).order_by(Customer.next_followup_time.asc()).all()
    
    return {
        "count": len(scheduled),
        "hours": hours,
        "scheduled_followups": [
            {
                "customer_id": c.id,
                "wa_id": c.wa_id,
                "name": c.name,
                "last_message_type": c.last_message_type,
                "next_followup_time": c.next_followup_time.isoformat() if c.next_followup_time else None,
                "minutes_until": int((c.next_followup_time - now).total_seconds() / 60) if c.next_followup_time else None,
            }
            for c in scheduled
        ]
    }


@router.get("/stats")
def get_followup_stats(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get follow-up statistics for the last N days"""
    from sqlalchemy import func
    
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Count follow-up messages sent
    followup_messages = db.query(Message).filter(
        Message.body.contains("Follow-Up"),
        Message.timestamp >= start_date
    ).count()
    
    # Count customers in different states
    followup1_sent = db.query(Customer).filter(
        Customer.last_message_type.ilike("%follow_up_1_sent%")
    ).count()
    
    followup2_sent = db.query(Customer).filter(
        Customer.last_message_type.ilike("%follow_up_2_sent%")
    ).count()
    
    # Count scheduled follow-ups
    scheduled = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None)
    ).count()
    
    # Count overdue follow-ups
    overdue = db.query(Customer).filter(
        Customer.next_followup_time.isnot(None),
        Customer.next_followup_time < now
    ).count()
    
    return {
        "period_days": days,
        "messages_sent": followup_messages,
        "customer_states": {
            "followup1_sent": followup1_sent,
            "followup2_sent": followup2_sent,
        },
        "scheduled": {
            "total": scheduled,
            "overdue": overdue,
            "upcoming": scheduled - overdue,
        }
    }

