"""
Analytics Controller - KPI Dashboard APIs
Provides comprehensive analytics for customers, leads, campaigns, orders, and flows
"""

from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_, distinct, extract

from database.db import get_db
from models.models import (
    Customer, Lead, Campaign, Order, Payment, Message,
    FlowLog, CampaignLog, Job, JobStatus, User, CampaignRecipient
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def _parse_date(val: Optional[str]) -> Optional[date]:
    """Parse date string in YYYY-MM-DD format"""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except Exception:
        return None


# ============================================================================
# DASHBOARD OVERVIEW - Single API for all key metrics
# ============================================================================

@router.get("/dashboard")
def get_dashboard_overview(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    """
    Get complete dashboard overview with all key metrics.
    Returns counts for today, this week, this month, and all-time.
    """
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)

        # Parse custom date range if provided
        dt_from = _parse_date(date_from) if date_from else None
        dt_to = _parse_date(date_to) if date_to else None

        # Customer counts
        total_customers = db.query(func.count(Customer.id)).scalar() or 0
        customers_today = db.query(func.count(Customer.id)).filter(
            Customer.created_at >= today_start
        ).scalar() or 0
        customers_this_week = db.query(func.count(Customer.id)).filter(
            Customer.created_at >= week_start
        ).scalar() or 0
        customers_this_month = db.query(func.count(Customer.id)).filter(
            Customer.created_at >= month_start
        ).scalar() or 0

        # Lead counts
        total_leads = db.query(func.count(Lead.id)).scalar() or 0
        leads_today = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= today_start
        ).scalar() or 0
        leads_this_week = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= week_start
        ).scalar() or 0
        leads_this_month = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= month_start
        ).scalar() or 0

        # Campaign counts
        total_campaigns = db.query(func.count(Campaign.id)).scalar() or 0
        campaigns_this_month = db.query(func.count(Campaign.id)).filter(
            Campaign.created_at >= month_start
        ).scalar() or 0

        # Order counts
        total_orders = db.query(func.count(Order.id)).scalar() or 0
        orders_today = db.query(func.count(Order.id)).filter(
            Order.timestamp >= today_start
        ).scalar() or 0

        # Message counts
        total_messages = db.query(func.count(Message.id)).scalar() or 0
        messages_today = db.query(func.count(Message.id)).filter(
            Message.timestamp >= today_start
        ).scalar() or 0

        # Flow completion counts
        flow_completions_today = db.query(func.count(FlowLog.id)).filter(
            and_(
                FlowLog.created_at >= today_start,
                FlowLog.step == "result",
                FlowLog.status_code == 200
            )
        ).scalar() or 0

        return {
            "success": True,
            "generated_at": now.isoformat(),
            "summary": {
                "customers": {
                    "total": total_customers,
                    "today": customers_today,
                    "this_week": customers_this_week,
                    "this_month": customers_this_month
                },
                "leads": {
                    "total": total_leads,
                    "today": leads_today,
                    "this_week": leads_this_week,
                    "this_month": leads_this_month
                },
                "campaigns": {
                    "total": total_campaigns,
                    "this_month": campaigns_this_month
                },
                "orders": {
                    "total": total_orders,
                    "today": orders_today
                },
                "messages": {
                    "total": total_messages,
                    "today": messages_today
                },
                "flow_completions": {
                    "today": flow_completions_today
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CUSTOMER ANALYTICS
# ============================================================================

@router.get("/customers")
def get_customer_analytics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get detailed customer analytics"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)

        # Total counts
        total = db.query(func.count(Customer.id)).scalar() or 0

        # Status breakdown
        status_counts = db.query(
            Customer.customer_status,
            func.count(Customer.id)
        ).group_by(Customer.customer_status).all()

        status_breakdown = {str(status): count for status, count in status_counts}

        # Time-based counts
        today = db.query(func.count(Customer.id)).filter(
            Customer.created_at >= today_start
        ).scalar() or 0

        this_week = db.query(func.count(Customer.id)).filter(
            Customer.created_at >= week_start
        ).scalar() or 0

        this_month = db.query(func.count(Customer.id)).filter(
            Customer.created_at >= month_start
        ).scalar() or 0

        # Assigned vs unassigned
        assigned = db.query(func.count(Customer.id)).filter(
            Customer.user_id.isnot(None)
        ).scalar() or 0
        unassigned = total - assigned

        # Customers with orders
        customers_with_orders = db.query(func.count(distinct(Order.customer_id))).scalar() or 0

        # Daily trend (last 30 days)
        thirty_days_ago = today_start - timedelta(days=30)
        daily_trend = db.query(
            func.date(Customer.created_at).label("date"),
            func.count(Customer.id).label("count")
        ).filter(
            Customer.created_at >= thirty_days_ago
        ).group_by(func.date(Customer.created_at)).order_by("date").all()

        return {
            "success": True,
            "total": total,
            "time_breakdown": {
                "today": today,
                "this_week": this_week,
                "this_month": this_month
            },
            "status_breakdown": status_breakdown,
            "assignment": {
                "assigned": assigned,
                "unassigned": unassigned
            },
            "engagement": {
                "with_orders": customers_with_orders,
                "without_orders": total - customers_with_orders
            },
            "daily_trend": [
                {"date": str(d), "count": c} for d, c in daily_trend
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LEAD ANALYTICS
# ============================================================================

@router.get("/leads")
def get_lead_analytics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get detailed lead analytics including source breakdown and city analysis"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)

        # Apply date filters if provided
        dt_from = datetime.combine(_parse_date(date_from), datetime.min.time()) if date_from else None
        dt_to = datetime.combine(_parse_date(date_to), datetime.max.time()) if date_to else None

        # Base query
        base_query = db.query(Lead)
        if dt_from:
            base_query = base_query.filter(Lead.created_at >= dt_from)
        if dt_to:
            base_query = base_query.filter(Lead.created_at <= dt_to)

        # Total leads
        total = base_query.count()

        # Time-based counts (without custom date filter)
        today = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= today_start
        ).scalar() or 0

        this_week = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= week_start
        ).scalar() or 0

        this_month = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= month_start
        ).scalar() or 0

        # Source breakdown
        source_counts = base_query.with_entities(
            Lead.lead_source,
            func.count(Lead.id)
        ).group_by(Lead.lead_source).all()

        source_breakdown = {(source or "Unknown"): count for source, count in source_counts}

        # City breakdown (top 10)
        city_counts = base_query.with_entities(
            Lead.city,
            func.count(Lead.id)
        ).group_by(Lead.city).order_by(func.count(Lead.id).desc()).limit(10).all()

        city_breakdown = [
            {"city": city or "Unknown", "count": count}
            for city, count in city_counts
        ]

        # Concern/Treatment breakdown (top 10)
        concern_counts = base_query.with_entities(
            Lead.zoho_mapped_concern,
            func.count(Lead.id)
        ).filter(Lead.zoho_mapped_concern.isnot(None)).group_by(
            Lead.zoho_mapped_concern
        ).order_by(func.count(Lead.id).desc()).limit(10).all()

        concern_breakdown = [
            {"concern": concern, "count": count}
            for concern, count in concern_counts
        ]

        # Daily trend (last 30 days)
        thirty_days_ago = today_start - timedelta(days=30)
        daily_trend = db.query(
            func.date(Lead.created_at).label("date"),
            func.count(Lead.id).label("count")
        ).filter(
            Lead.created_at >= thirty_days_ago
        ).group_by(func.date(Lead.created_at)).order_by("date").all()

        # Hourly distribution (for understanding peak times)
        hourly_dist = db.query(
            extract('hour', Lead.created_at).label("hour"),
            func.count(Lead.id).label("count")
        ).group_by(extract('hour', Lead.created_at)).order_by("hour").all()

        return {
            "success": True,
            "total": total,
            "time_breakdown": {
                "today": today,
                "this_week": this_week,
                "this_month": this_month
            },
            "source_breakdown": source_breakdown,
            "city_breakdown": city_breakdown,
            "concern_breakdown": concern_breakdown,
            "daily_trend": [
                {"date": str(d), "count": c} for d, c in daily_trend
            ],
            "hourly_distribution": [
                {"hour": int(h), "count": c} for h, c in hourly_dist
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CAMPAIGN ANALYTICS
# ============================================================================

@router.get("/campaigns")
def get_campaign_analytics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get campaign performance analytics"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)

        # Total campaigns
        total_campaigns = db.query(func.count(Campaign.id)).scalar() or 0

        # Campaigns this month
        campaigns_this_month = db.query(func.count(Campaign.id)).filter(
            Campaign.created_at >= month_start
        ).scalar() or 0

        # Campaign type breakdown
        type_counts = db.query(
            Campaign.type,
            func.count(Campaign.id)
        ).group_by(Campaign.type).all()

        type_breakdown = {str(t): c for t, c in type_counts}

        # Campaign logs analysis
        total_messages_sent = db.query(func.count(CampaignLog.id)).scalar() or 0

        status_counts = db.query(
            CampaignLog.status,
            func.count(CampaignLog.id)
        ).group_by(CampaignLog.status).all()

        message_status = {status: count for status, count in status_counts}
        success_count = message_status.get("success", 0)
        failure_count = message_status.get("failure", 0)

        success_rate = round((success_count / total_messages_sent * 100), 2) if total_messages_sent > 0 else 0

        # Messages today
        messages_today = db.query(func.count(CampaignLog.id)).filter(
            CampaignLog.created_at >= today_start
        ).scalar() or 0

        # Top 5 campaigns by message count
        top_campaigns = db.query(
            Campaign.name,
            func.count(CampaignLog.id).label("message_count")
        ).join(CampaignLog, Campaign.id == CampaignLog.campaign_id).group_by(
            Campaign.id, Campaign.name
        ).order_by(func.count(CampaignLog.id).desc()).limit(5).all()

        return {
            "success": True,
            "total_campaigns": total_campaigns,
            "campaigns_this_month": campaigns_this_month,
            "type_breakdown": type_breakdown,
            "messaging": {
                "total_sent": total_messages_sent,
                "today": messages_today,
                "success": success_count,
                "failure": failure_count,
                "success_rate": success_rate
            },
            "top_campaigns": [
                {"name": name, "message_count": count}
                for name, count in top_campaigns
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FLOW ANALYTICS (Treatment + Lead Appointment)
# ============================================================================

@router.get("/flows")
def get_flow_analytics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get flow completion and drop-off analytics"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())

        # Apply date filters
        dt_from = datetime.combine(_parse_date(date_from), datetime.min.time()) if date_from else None
        dt_to = datetime.combine(_parse_date(date_to), datetime.max.time()) if date_to else None

        base_query = db.query(FlowLog)
        if dt_from:
            base_query = base_query.filter(FlowLog.created_at >= dt_from)
        if dt_to:
            base_query = base_query.filter(FlowLog.created_at <= dt_to)

        # Flow type breakdown
        flow_type_counts = base_query.with_entities(
            FlowLog.flow_type,
            func.count(distinct(FlowLog.wa_id))
        ).group_by(FlowLog.flow_type).all()

        flow_breakdown = {ft: count for ft, count in flow_type_counts}

        # Step breakdown (shows where users drop off)
        step_counts = base_query.with_entities(
            FlowLog.flow_type,
            FlowLog.step,
            func.count(distinct(FlowLog.wa_id))
        ).group_by(FlowLog.flow_type, FlowLog.step).all()

        step_breakdown = {}
        for flow_type, step, count in step_counts:
            if flow_type not in step_breakdown:
                step_breakdown[flow_type] = {}
            step_breakdown[flow_type][step or "unknown"] = count

        # Completions (step = "result" with status 200)
        completions = base_query.filter(
            and_(
                FlowLog.step == "result",
                FlowLog.status_code == 200
            )
        ).with_entities(
            FlowLog.flow_type,
            func.count(distinct(FlowLog.wa_id))
        ).group_by(FlowLog.flow_type).all()

        completion_counts = {ft: count for ft, count in completions}

        # Calculate completion rates
        completion_rates = {}
        for flow_type, total in flow_breakdown.items():
            completed = completion_counts.get(flow_type, 0)
            rate = round((completed / total * 100), 2) if total > 0 else 0
            completion_rates[flow_type] = {
                "total_started": total,
                "completed": completed,
                "completion_rate": rate
            }

        # Today's flows
        flows_today = db.query(
            FlowLog.flow_type,
            func.count(distinct(FlowLog.wa_id))
        ).filter(
            FlowLog.created_at >= today_start
        ).group_by(FlowLog.flow_type).all()

        today_breakdown = {ft: count for ft, count in flows_today}

        # Daily trend (last 14 days)
        fourteen_days_ago = today_start - timedelta(days=14)
        daily_trend = db.query(
            func.date(FlowLog.created_at).label("date"),
            FlowLog.flow_type,
            func.count(distinct(FlowLog.wa_id)).label("count")
        ).filter(
            FlowLog.created_at >= fourteen_days_ago
        ).group_by(func.date(FlowLog.created_at), FlowLog.flow_type).order_by("date").all()

        trend_data = {}
        for d, flow_type, count in daily_trend:
            date_str = str(d)
            if date_str not in trend_data:
                trend_data[date_str] = {"date": date_str}
            trend_data[date_str][flow_type] = count

        return {
            "success": True,
            "flow_breakdown": flow_breakdown,
            "step_breakdown": step_breakdown,
            "completion_rates": completion_rates,
            "today": today_breakdown,
            "daily_trend": list(trend_data.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ORDER & PAYMENT ANALYTICS
# ============================================================================

@router.get("/orders")
def get_order_analytics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get order and payment analytics"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)

        # Total orders
        total_orders = db.query(func.count(Order.id)).scalar() or 0

        # Orders by status
        status_counts = db.query(
            Order.status,
            func.count(Order.id)
        ).group_by(Order.status).all()

        status_breakdown = {status: count for status, count in status_counts}

        # Orders today
        orders_today = db.query(func.count(Order.id)).filter(
            Order.timestamp >= today_start
        ).scalar() or 0

        # Orders this month
        orders_this_month = db.query(func.count(Order.id)).filter(
            Order.timestamp >= month_start
        ).scalar() or 0

        # Payment analytics
        total_payments = db.query(func.count(Payment.id)).scalar() or 0

        payment_status_counts = db.query(
            Payment.status,
            func.count(Payment.id),
            func.sum(Payment.amount)
        ).group_by(Payment.status).all()

        payment_breakdown = {
            status: {"count": count, "amount": float(amount or 0)}
            for status, count, amount in payment_status_counts
        }

        # Total revenue (paid payments)
        total_revenue = db.query(func.sum(Payment.amount)).filter(
            Payment.status == "paid"
        ).scalar() or 0

        # Revenue today
        revenue_today = db.query(func.sum(Payment.amount)).filter(
            and_(
                Payment.status == "paid",
                Payment.created_at >= today_start
            )
        ).scalar() or 0

        # Revenue this month
        revenue_this_month = db.query(func.sum(Payment.amount)).filter(
            and_(
                Payment.status == "paid",
                Payment.created_at >= month_start
            )
        ).scalar() or 0

        return {
            "success": True,
            "orders": {
                "total": total_orders,
                "today": orders_today,
                "this_month": orders_this_month,
                "status_breakdown": status_breakdown
            },
            "payments": {
                "total": total_payments,
                "breakdown": payment_breakdown
            },
            "revenue": {
                "total": float(total_revenue),
                "today": float(revenue_today),
                "this_month": float(revenue_this_month)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MESSAGE ANALYTICS
# ============================================================================

@router.get("/messages")
def get_message_analytics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get messaging analytics"""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())

        # Total messages
        total = db.query(func.count(Message.id)).scalar() or 0

        # Messages today
        today = db.query(func.count(Message.id)).filter(
            Message.timestamp >= today_start
        ).scalar() or 0

        # Messages this week
        this_week = db.query(func.count(Message.id)).filter(
            Message.timestamp >= week_start
        ).scalar() or 0

        # Sender type breakdown
        sender_counts = db.query(
            Message.sender_type,
            func.count(Message.id)
        ).group_by(Message.sender_type).all()

        sender_breakdown = {(sender or "unknown"): count for sender, count in sender_counts}

        # Message type breakdown
        type_counts = db.query(
            Message.type,
            func.count(Message.id)
        ).group_by(Message.type).all()

        type_breakdown = {(t or "unknown"): count for t, count in type_counts}

        # Unique customers today
        unique_customers_today = db.query(
            func.count(distinct(Message.customer_id))
        ).filter(
            Message.timestamp >= today_start
        ).scalar() or 0

        # Daily trend (last 14 days)
        fourteen_days_ago = today_start - timedelta(days=14)
        daily_trend = db.query(
            func.date(Message.timestamp).label("date"),
            func.count(Message.id).label("count")
        ).filter(
            Message.timestamp >= fourteen_days_ago
        ).group_by(func.date(Message.timestamp)).order_by("date").all()

        # Hourly distribution
        hourly_dist = db.query(
            extract('hour', Message.timestamp).label("hour"),
            func.count(Message.id).label("count")
        ).filter(
            Message.timestamp >= today_start
        ).group_by(extract('hour', Message.timestamp)).order_by("hour").all()

        return {
            "success": True,
            "total": total,
            "today": today,
            "this_week": this_week,
            "unique_customers_today": unique_customers_today,
            "sender_breakdown": sender_breakdown,
            "type_breakdown": type_breakdown,
            "daily_trend": [
                {"date": str(d), "count": c} for d, c in daily_trend
            ],
            "hourly_distribution_today": [
                {"hour": int(h), "count": c} for h, c in hourly_dist
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# USER/AGENT PERFORMANCE
# ============================================================================

@router.get("/agents")
def get_agent_analytics(
    db: Session = Depends(get_db),
):
    """Get agent performance analytics"""
    try:
        # Agent customer counts
        agent_customers = db.query(
            User.id,
            User.first_name,
            User.last_name,
            func.count(Customer.id).label("customer_count")
        ).outerjoin(Customer, Customer.user_id == User.id).group_by(
            User.id, User.first_name, User.last_name
        ).all()

        agent_stats = []
        for user_id, first_name, last_name, customer_count in agent_customers:
            # Get resolved count for this agent
            resolved = db.query(func.count(Customer.id)).filter(
                and_(
                    Customer.user_id == user_id,
                    Customer.customer_status == "resolved"
                )
            ).scalar() or 0

            agent_stats.append({
                "agent_id": str(user_id),
                "name": f"{first_name} {last_name}".strip(),
                "total_customers": customer_count,
                "resolved": resolved,
                "pending": customer_count - resolved
            })

        # Sort by total customers
        agent_stats.sort(key=lambda x: x["total_customers"], reverse=True)

        return {
            "success": True,
            "agents": agent_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONVERSION FUNNEL
# ============================================================================

@router.get("/funnel")
def get_conversion_funnel(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query("lead_appointment", description="treatment or lead_appointment"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Get conversion funnel analysis showing drop-off at each step.
    """
    try:
        # Define funnel steps in order
        funnel_steps = ["entry", "city_selection", "treatment", "concern_list", "last_step", "result"]

        # Apply date filters
        dt_from = datetime.combine(_parse_date(date_from), datetime.min.time()) if date_from else None
        dt_to = datetime.combine(_parse_date(date_to), datetime.max.time()) if date_to else None

        base_query = db.query(FlowLog).filter(FlowLog.flow_type == flow_type)
        if dt_from:
            base_query = base_query.filter(FlowLog.created_at >= dt_from)
        if dt_to:
            base_query = base_query.filter(FlowLog.created_at <= dt_to)

        # Get unique user count for each step
        step_counts = base_query.with_entities(
            FlowLog.step,
            func.count(distinct(FlowLog.wa_id))
        ).group_by(FlowLog.step).all()

        step_map = {step: count for step, count in step_counts}

        # Build funnel data
        funnel_data = []
        prev_count = None
        for step in funnel_steps:
            count = step_map.get(step, 0)
            drop_off = prev_count - count if prev_count is not None else 0
            drop_off_rate = round((drop_off / prev_count * 100), 2) if prev_count and prev_count > 0 else 0

            funnel_data.append({
                "step": step,
                "users": count,
                "drop_off": drop_off,
                "drop_off_rate": drop_off_rate
            })
            prev_count = count

        # Overall conversion rate
        total_started = step_map.get("entry", 0) or step_map.get(funnel_steps[0], 0)
        total_completed = step_map.get("result", 0)
        overall_conversion = round((total_completed / total_started * 100), 2) if total_started > 0 else 0

        return {
            "success": True,
            "flow_type": flow_type,
            "funnel": funnel_data,
            "summary": {
                "total_started": total_started,
                "total_completed": total_completed,
                "overall_conversion_rate": overall_conversion
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
