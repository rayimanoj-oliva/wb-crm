from datetime import datetime, timedelta

from sqlalchemy import func, case, cast, Date
from sqlalchemy.orm import Session

from models.models import Customer, Order, Campaign, Message, Job, JobStatus, Template, OrderItem


def get_dashboard_metrics(db: Session):
    metrics = {}

    # Summary KPIs
    metrics['total_customers'] = db.query(func.count(Customer.id)).scalar()
    metrics['total_orders'] = db.query(func.count(Order.id)).scalar()
    metrics['active_campaigns'] = db.query(func.count(Campaign.id)).scalar()
    metrics['messages_sent_today'] = db.query(func.count(Message.id)).filter(func.date(Message.timestamp) == func.current_date()).scalar()

    # Delivery Success Rate
    success_count = db.query(func.count()).filter(JobStatus.status == 'success').scalar()
    failure_count = db.query(func.count()).filter(JobStatus.status == 'failure').scalar()
    total = success_count + failure_count
    metrics['delivery_success_rate'] = (success_count / total) * 100 if total > 0 else 0

    # Templates Used
    metrics['templates_used'] = db.query(func.count(Template.template_name)).scalar()

    return metrics


def get_recent_activity(db: Session, limit=10):
    recent = {
        "new_customers": db.query(Customer).order_by(Customer.id.desc()).limit(limit).all(),
        "recent_orders": db.query(Order).order_by(Order.timestamp.desc()).limit(limit).all(),
        "recent_messages": db.query(Message).order_by(Message.timestamp.desc()).limit(limit).all(),
        "recent_campaigns": db.query(Campaign).order_by(Campaign.created_at.desc()).limit(limit).all(),
    }
    return recent


def get_campaign_performance(db: Session):
    campaigns = db.query(
        Campaign.id,
        Campaign.name,
        func.count(JobStatus.customer_id).label("total_recipients"),
        func.sum(func.case([(JobStatus.status == "success", 1)], else_=0)).label("success"),
        func.sum(func.case([(JobStatus.status == "failure", 1)], else_=0)).label("failure"),
    ).join(Job).join(JobStatus).group_by(Campaign.id).all()

    result = []
    for c in campaigns:
        success_rate = (c.success / (c.success + c.failure)) * 100 if (c.success + c.failure) else 0
        result.append({
            "id": c.id,
            "name": c.name,
            "total_recipients": c.total_recipients,
            "success": c.success,
            "failure": c.failure,
            "success_rate": success_rate
        })
    return result


def get_order_stats(db: Session):
    total_revenue = db.query(func.sum(OrderItem.item_price)).scalar() or 0
    average_order_value = db.query(func.avg(OrderItem.item_price)).scalar() or 0
    return {
        "total_revenue": total_revenue,
        "average_order_value": average_order_value
    }


def get_message_type_distribution(db: Session):
    types = db.query(
        Message.type,
        func.count(Message.id)
    ).group_by(Message.type).all()
    return [{"type": t[0], "count": t[1]} for t in types]

from models.models import campaign_customers  # ensure this is imported

def get_messages_per_campaign(db: Session):
    result = (
        db.query(
            Campaign.name,
            func.count(Message.id).label("messages_sent")
        )
        .join(campaign_customers, campaign_customers.c.campaign_id == Campaign.id)
        .join(Customer, Customer.id == campaign_customers.c.customer_id)
        .join(Message, Message.customer_id == Customer.id)
        .group_by(Campaign.name)
        .all()
    )
    return [{"campaign": name, "messages_sent": count} for name, count in result]


def get_orders_over_time(db, days=30):
    start_date = datetime.utcnow() - timedelta(days=days)
    orders = db.query(
        cast(Order.timestamp, Date).label("date"),
        func.count(Order.id)
    ).filter(Order.timestamp >= start_date).group_by("date").order_by("date").all()

    return [{"date": str(date), "orders": count} for date, count in orders]

from sqlalchemy import case

def get_campaign_delivery_stats(db: Session):
    campaigns = (
        db.query(
            Campaign.name,
            func.sum(case((JobStatus.status == "success", 1), else_=0)).label("success"),
            func.sum(case((JobStatus.status == "failure", 1), else_=0)).label("failure")
        )
        .select_from(Campaign)
        .join(Job, Job.campaign_id == Campaign.id)
        .join(JobStatus, JobStatus.job_id == Job.id)
        .group_by(Campaign.name)
        .all()
    )

    return [{
        "campaign": c.name,
        "success": int(c.success or 0),
        "failure": int(c.failure or 0)
    } for c in campaigns]




def get_customer_growth_over_time(db, days=30):
    start_date = datetime.utcnow() - timedelta(days=30)
    customers = db.query(
        cast(Customer.created_at, Date).label("date"),
        func.count(Customer.id)
    ).filter(Customer.created_at >= start_date).group_by("date").order_by("date").all()

    return [{"date": str(date), "new_customers": count} for date, count in customers]