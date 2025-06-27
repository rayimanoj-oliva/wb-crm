# app/controllers/dashboard_controller.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import get_db
from services.dashboard_service import get_dashboard_metrics, get_recent_activity, get_campaign_performance, \
    get_order_stats, get_message_type_distribution, get_messages_per_campaign, get_orders_over_time, \
    get_campaign_delivery_stats, get_customer_growth_over_time

router = APIRouter(tags=["Dashboard"])


@router.get("/metrics")
def dashboard_metrics(db: Session = Depends(get_db)):
    return get_dashboard_metrics(db)


@router.get("/recent-activity")
def recent_activity(db: Session = Depends(get_db)):
    return get_recent_activity(db)


@router.get("/campaign-performance")
def campaign_performance(db: Session = Depends(get_db)):
    return get_campaign_performance(db)


@router.get("/order-stats")
def order_statistics(db: Session = Depends(get_db)):
    return get_order_stats(db)


@router.get("/message-types")
def message_type_stats(db: Session = Depends(get_db)):
    return get_message_type_distribution(db)


@router.get("/charts/messages-per-campaign")
def chart_messages_per_campaign(db: Session = Depends(get_db)):
    return get_messages_per_campaign(db)


@router.get("/charts/orders-over-time")
def chart_orders_over_time(db: Session = Depends(get_db)):
    return get_orders_over_time(db)


@router.get("/charts/message-type-distribution")
def chart_message_type_distribution(db: Session = Depends(get_db)):
    return get_message_type_distribution(db)


@router.get("/charts/campaign-delivery")
def chart_campaign_delivery(db: Session = Depends(get_db)):
    return get_campaign_delivery_stats(db)


@router.get("/charts/customer-growth")
def chart_customer_growth(db: Session = Depends(get_db)):
    return get_customer_growth_over_time(db)
