from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta

from models.models import Message, Customer, ReferrerTracking, Lead
from clients.schema import AppointmentQuery
import clients.service as client_service
from models.models import Template, JobStatus, Campaign, Job, CampaignRecipient
from sqlalchemy import case, and_, or_


def get_today_metrics(db: Session):
    today = date.today()

    # Get new conversations (messages created today)
    new_conversations = db.query(Message).filter(
        Message.timestamp >= datetime.combine(today, datetime.min.time()),
        Message.timestamp <= datetime.combine(today, datetime.max.time())
    ).count()

    # Get new customers created today
    new_customers = db.query(Customer).filter(
        Customer.created_at >= datetime.combine(today, datetime.min.time()),
        Customer.created_at <= datetime.combine(today, datetime.max.time())
    ).count()

    return {
        "new_conversations": new_conversations,
        "new_customers": new_customers
    }



def get_total_customers(db: Session):
    return db.query(Customer).count()


def get_appointments_booked_today(center_id: Optional[str] = None, db: Session = None):
    """
    Count appointments booked today from treatment flow.
    An appointment is considered booked when:
    1. User reaches the "Thank you" message step
    2. A lead was successfully created (NOT a duplicate)
    
    We count appointments that have corresponding non-duplicate leads created today.
    This ensures we only count bookings where leads were actually pushed to Zoho.
    """
    if db is None:
        return 0
    
    today = date.today()
    
    # Count appointments from ReferrerTracking where:
    # 1. is_appointment_booked = True (appointment was booked)
    # 2. created_at is today (booked today)
    # 3. There exists a corresponding Lead record created today with same wa_id (non-duplicate lead)
    #    - We check for leads created today with same wa_id
    #    - If a lead exists, it means it was successfully created (not a duplicate)
    #    - Duplicate leads are not created, so if no lead exists, it was a duplicate
    
    base_query = db.query(ReferrerTracking).filter(
        ReferrerTracking.is_appointment_booked == True,
        func.date(ReferrerTracking.created_at) == today
    )
    
    # Join with Lead table to ensure appointment has a corresponding non-duplicate lead
    # A lead exists only if it was successfully created (not a duplicate)
    query = base_query.join(
        Lead,
        (ReferrerTracking.wa_id == Lead.wa_id) &
        (func.date(Lead.created_at) == today)
    ).distinct()
    
    # Optionally filter by center_id if provided
    if center_id:
        # Try to match center_id with center_name or location
        query = query.filter(
            (ReferrerTracking.center_name.ilike(f"%{center_id}%")) |
            (ReferrerTracking.location.ilike(f"%{center_id}%"))
        )
    
    count = query.count()
    return count

def get_agent_avg_response_time(agent_id: str, center_id: Optional[str], db: Session) -> Optional[float]:
    """
    Calculates the average time taken by a specific agent to reply to a customer message.

    The function uses the 'agent_id' and the optional 'center_id' to filter messages.

    :param agent_id: The ID of the agent whose response time is being measured.
    :param center_id: The ID of the center to filter messages by. Optional.
    :param db: The database session.
    :return: The average response time in seconds, or None if no agent replies are found.
    """
    # Start with a base query for all messages related to the agent
    query = db.query(Message).filter(
        Message.agent_id == agent_id
    )

    # If a center_id is provided, add the filter
    if center_id:
        query = query.filter(Message.center_id == center_id)

    # Order the messages by timestamp for accurate calculation
    messages = query.order_by(Message.timestamp).all()

    if not messages:
        return None

    response_times = []
    last_customer_message_time = None

    for message in messages:
        # Check if the current message is from a customer
        if message.sender_type == "customer":
            last_customer_message_time = message.timestamp
        # Check if the current message is from the specified agent and we have a preceding customer message
        elif message.sender_type == "agent" and message.agent_id == agent_id and last_customer_message_time:
            # Calculate the time difference
            time_diff: timedelta = message.timestamp - last_customer_message_time
            response_times.append(time_diff.total_seconds())
            # Reset the last customer message time, as this response concludes the sequence
            last_customer_message_time = None

    if not response_times:
        return None  # No agent replies found

    # Calculate the average response time
    avg_response_time = sum(response_times) / len(response_times)
    return avg_response_time
def get_template_status(db: Session):
    """
    Returns counts of approved, pending, and rejected templates
    """
    # Status stored from Meta is typically uppercase (e.g., "APPROVED", "PENDING", "REJECTED").
    # Normalize to lowercase for robust matching.
    status_expr = func.lower(Template.template_body["status"].astext)

    approved = db.query(Template).filter(status_expr == "approved").count()

    # Treat various review-like states as pending review
    pending_statuses = ["pending", "in_appeal", "in_review", "review"]
    pending = db.query(Template).filter(status_expr.in_(pending_statuses)).count()

    rejected = db.query(Template).filter(status_expr == "rejected").count()

    return {
        "approved": approved,
        "pending": pending,
        "failed": rejected,
    }


def get_recent_failed_messages(db: Session):
    """
    Returns counts of different failure reasons from recent messages.
    We check messages from the last 30 days that contain error-related text.
    """
    from datetime import timedelta
    from sqlalchemy import or_
    
    # Get date range for recent messages (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Count unapproved template errors
    # Check for various error message patterns
    unapproved_template = db.query(Message).filter(
        Message.timestamp >= thirty_days_ago,
        or_(
            Message.body.ilike("%unapproved template%"),
            Message.body.ilike("%template not approved%"),
            Message.body.ilike("%invalid template%"),
            Message.body.ilike("%template.*not.*approved%"),
            Message.body.ilike("%template.*error%"),
            Message.body.ilike("%template.*failed%")
        )
    ).count()
    
    # Count user opted out errors
    user_opted_out = db.query(Message).filter(
        Message.timestamp >= thirty_days_ago,
        or_(
            Message.body.ilike("%opted out%"),
            Message.body.ilike("%opt.*out%"),
            Message.body.ilike("%user.*opted%"),
            Message.body.ilike("%recipient.*opted%"),
            Message.body.ilike("%user opted%")
        )
    ).count()
    
    # Count invalid phone number errors
    invalid_phone = db.query(Message).filter(
        Message.timestamp >= thirty_days_ago,
        or_(
            Message.body.ilike("%invalid phone%"),
            Message.body.ilike("%invalid.*phone%"),
            Message.body.ilike("%phone.*invalid%"),
            Message.body.ilike("%invalid.*number%"),
            Message.body.ilike("%phone.*number.*invalid%"),
            Message.body.ilike("%That doesn't look like a valid%"),
            Message.body.ilike("%valid.*mobile.*number%")
        )
    ).count()
    
    return {
        "unapproved_template_used": unapproved_template,
        "user_opted_out": user_opted_out,
        "invalid_phone_number": invalid_phone
    }


def get_campaign_performance_summary(db: Session):
    """
    Returns overall campaign performance summary statistics.
    Calculates sent, delivered, read, and replied counts across all campaigns.
    """
    # Count total sent (all JobStatus records + all CampaignRecipient records)
    total_sent_customers = db.query(JobStatus).count()
    total_sent_recipients = db.query(CampaignRecipient).filter(
        CampaignRecipient.status.in_(["SENT", "FAILED", "QUEUED"])
    ).count()
    total_sent = total_sent_customers + total_sent_recipients
    
    # Count delivered (success status in JobStatus + SENT status in CampaignRecipient)
    total_delivered_customers = db.query(JobStatus).filter(
        JobStatus.status == "success"
    ).count()
    total_delivered_recipients = db.query(CampaignRecipient).filter(
        CampaignRecipient.status == "SENT"
    ).count()
    total_delivered = total_delivered_customers + total_delivered_recipients
    
    # Calculate delivered percentage
    delivered_percentage = (total_delivered / total_sent * 100) if total_sent > 0 else 0
    
    # For read count: We'll estimate based on messages sent after campaign messages
    # This is a simplified approach - in production, you'd track read receipts from WhatsApp webhooks
    # Count messages from customers who received campaign messages (within 7 days of campaign)
    from datetime import timedelta
    seven_days_ago = datetime.now() - timedelta(days=7)
    
    # Get customers who received campaign messages
    campaign_customer_ids = db.query(JobStatus.customer_id).distinct().all()
    campaign_customer_ids_list = [cid[0] for cid in campaign_customer_ids]
    
    # Count messages from these customers after campaign (as a proxy for "read")
    total_read = 0
    if campaign_customer_ids_list:
        total_read = db.query(Message).filter(
            Message.customer_id.in_(campaign_customer_ids_list),
            Message.sender_type == "customer",
            Message.timestamp >= seven_days_ago
        ).count()
    
    # Calculate read percentage
    read_percentage = (total_read / total_delivered * 100) if total_delivered > 0 else 0
    
    # For replied count: Count customers who sent messages after receiving campaign
    # This is also a simplified approach
    total_replied = 0
    if campaign_customer_ids_list:
        # Count unique customers who replied
        total_replied = db.query(Message.customer_id).filter(
            Message.customer_id.in_(campaign_customer_ids_list),
            Message.sender_type == "customer",
            Message.timestamp >= seven_days_ago
        ).distinct().count()
    
    # Calculate replied percentage
    replied_percentage = (total_replied / total_delivered * 100) if total_delivered > 0 else 0
    
    return {
        "sent": total_sent,
        "delivered": total_delivered,
        "delivered_percentage": round(delivered_percentage, 1),
        "read": total_read,
        "read_percentage": round(read_percentage, 1),
        "replied": total_replied,
        "replied_percentage": round(replied_percentage, 1)
    }


def get_dashboard_summary(db: Session, campaign_limit: int = 10):
    """
    Unified dashboard API that returns all dashboard data in a single call.
    This eliminates 7 separate API calls from the frontend.
    """
    # Get today metrics
    today = date.today()
    new_conversations = db.query(Message).filter(
        Message.timestamp >= datetime.combine(today, datetime.min.time()),
        Message.timestamp <= datetime.combine(today, datetime.max.time())
    ).count()
    new_customers = db.query(Customer).filter(
        Customer.created_at >= datetime.combine(today, datetime.min.time()),
        Customer.created_at <= datetime.combine(today, datetime.max.time())
    ).count()

    # Get total customers
    total_customers = db.query(Customer).count()

    # Get appointments booked today (reuse existing function)
    appointments_today = get_appointments_booked_today(db=db)

    # Get template status
    template_status = get_template_status(db)

    # Get recent failed messages
    failed_messages = get_recent_failed_messages(db)

    # Get campaign performance summary
    campaign_summary = get_campaign_performance_summary(db)

    # Get campaign list
    campaign_list = get_campaign_performance_list(db, limit=campaign_limit)

    return {
        "today_metrics": {
            "new_conversations": new_conversations,
            "new_customers": new_customers
        },
        "total_customers": total_customers,
        "appointments_today": {
            "count": appointments_today,
            "percentage": 0
        },
        "template_status": template_status,
        "failed_messages": failed_messages,
        "campaign_summary": campaign_summary,
        "campaign_list": campaign_list
    }


def get_campaign_performance_list(db: Session, limit: int = 10):
    """
    Returns list of campaigns with their performance metrics.
    Includes sent, delivered, read, replied counts, CTR, and ROI.
    """
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).limit(limit).all()
    
    campaign_list = []
    for campaign in campaigns:
        # Get all jobs for this campaign
        jobs = db.query(Job).filter(Job.campaign_id == campaign.id).all()
        job_ids = [job.id for job in jobs]
        
        if not job_ids:
            # No jobs yet, return zero stats
            campaign_list.append({
                "id": str(campaign.id),
                "name": campaign.name,
                "type": campaign.type,
                "description": campaign.description,
                "status": "pending",
                "sent": 0,
                "delivered": 0,
                "read": 0,
                "replied": 0,
                "ctr": 0.0,
                "roi": 0.0,
                "created_at": campaign.created_at.isoformat() if campaign.created_at else None
            })
            continue
        
        # Count sent (JobStatus records + CampaignRecipient records)
        sent_customers = db.query(JobStatus).filter(JobStatus.job_id.in_(job_ids)).count()
        sent_recipients = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status.in_(["SENT", "FAILED", "QUEUED"])
        ).count()
        total_sent = sent_customers + sent_recipients
        
        # Count delivered
        delivered_customers = db.query(JobStatus).filter(
            JobStatus.job_id.in_(job_ids),
            JobStatus.status == "success"
        ).count()
        delivered_recipients = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == "SENT"
        ).count()
        total_delivered = delivered_customers + delivered_recipients
        
        # Get customer IDs who received this campaign (from JobStatus)
        customer_ids = db.query(JobStatus.customer_id).filter(
            JobStatus.job_id.in_(job_ids)
        ).distinct().all()
        customer_ids_list = [cid[0] for cid in customer_ids]
        
        # Get phone numbers and wa_ids from CampaignRecipient for this campaign
        recipient_phones = db.query(CampaignRecipient.phone_number).filter(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == "SENT"
        ).distinct().all()
        recipient_phone_list = [phone[0] for phone in recipient_phones]
        
        # Get wa_ids from customers who received the campaign (for direct message matching)
        customer_wa_ids = []
        if customer_ids_list:
            customers = db.query(Customer.wa_id).filter(Customer.id.in_(customer_ids_list)).all()
            customer_wa_ids = [c[0] for c in customers if c[0]]
        
        # Also get customer IDs and wa_ids for recipients by matching phone numbers
        if recipient_phone_list:
            import re
            # Normalize recipient phone numbers to last 10 digits and full wa_id format
            normalized_recipient_phones = set()
            normalized_wa_ids = set()
            for phone in recipient_phone_list:
                digits = re.sub(r'\D', '', phone)
                if len(digits) >= 10:
                    last_10 = digits[-10:]
                    normalized_recipient_phones.add(last_10)
                    # Also create potential wa_id formats
                    normalized_wa_ids.add(last_10)  # Just the 10 digits
                    normalized_wa_ids.add('91' + last_10)  # With 91 prefix
                    normalized_wa_ids.add('+91' + last_10)  # With +91 prefix
            
            # Find customers by matching wa_id (which contains phone number)
            if normalized_recipient_phones:
                # Get all customers and check if their wa_id ends with recipient phone
                all_customers = db.query(Customer.id, Customer.wa_id).all()
                for cust_id, wa_id in all_customers:
                    if wa_id:
                        wa_id_digits = re.sub(r'\D', '', wa_id)
                        if len(wa_id_digits) >= 10:
                            last_10 = wa_id_digits[-10:]
                            if last_10 in normalized_recipient_phones:
                                if cust_id not in customer_ids_list:
                                    customer_ids_list.append(cust_id)
                                if wa_id not in customer_wa_ids:
                                    customer_wa_ids.append(wa_id)
            
            # Also add normalized wa_ids directly for message matching
            # This helps match messages even if customer record doesn't exist
            for wa_id_format in normalized_wa_ids:
                if wa_id_format not in customer_wa_ids:
                    customer_wa_ids.append(wa_id_format)
        
        # Get the latest job's timestamp to use as campaign send time
        from datetime import timedelta
        latest_job = db.query(Job).filter(Job.id.in_(job_ids)).order_by(
            func.coalesce(Job.last_triggered_time, Job.created_at).desc()
        ).first()
        
        # Determine campaign send time - use job timestamp or campaign created_at as fallback
        if latest_job:
            campaign_send_time = latest_job.last_triggered_time or latest_job.created_at
        else:
            campaign_send_time = campaign.created_at
        
        # If still None, use campaign created_at or default to 30 days ago
        if not campaign_send_time:
            campaign_send_time = campaign.created_at or (datetime.now() - timedelta(days=30))
        
        # Count read (messages from customers after campaign)
        # Read is estimated as any message from customer after campaign send time
        # We check both by customer_id and by wa_id to capture all messages
        total_read = 0
        read_conditions = []
        
        if customer_ids_list:
            read_conditions.append(Message.customer_id.in_(customer_ids_list))
        
        if customer_wa_ids:
            # Match by exact wa_id or by last 10 digits of wa_id
            import re
            wa_id_conditions = []
            exact_wa_ids = []
            last_10_digits_set = set()
            
            for wa_id in customer_wa_ids:
                wa_id_digits = re.sub(r'\D', '', wa_id)
                if len(wa_id_digits) >= 10:
                    last_10 = wa_id_digits[-10:]
                    last_10_digits_set.add(last_10)
                else:
                    exact_wa_ids.append(wa_id)
            
            # Add exact matches
            if exact_wa_ids:
                wa_id_conditions.append(Message.from_wa_id.in_(exact_wa_ids))
            
            # Add last 10 digits matches using LIKE pattern
            if last_10_digits_set:
                for last_10 in last_10_digits_set:
                    # Match any wa_id that ends with these 10 digits
                    wa_id_conditions.append(Message.from_wa_id.like(f'%{last_10}'))
            
            if wa_id_conditions:
                read_conditions.append(or_(*wa_id_conditions))
        
        if read_conditions:
            total_read = db.query(Message.id).filter(
                or_(*read_conditions),
                Message.sender_type == "customer",
                Message.timestamp >= campaign_send_time
            ).distinct().count()
        
        # Count replied (unique customers/wa_ids who sent messages after campaign)
        total_replied = 0
        replied_customer_ids = set()
        replied_wa_ids = set()
        
        if customer_ids_list or customer_wa_ids:
            # Get all messages from campaign recipients after campaign send time
            reply_conditions = []
            if customer_ids_list:
                reply_conditions.append(Message.customer_id.in_(customer_ids_list))
            
            if customer_wa_ids:
                # Match by exact wa_id or by last 10 digits of wa_id
                import re
                wa_id_conditions = []
                exact_wa_ids = []
                last_10_digits_set = set()
                
                for wa_id in customer_wa_ids:
                    wa_id_digits = re.sub(r'\D', '', wa_id)
                    if len(wa_id_digits) >= 10:
                        last_10 = wa_id_digits[-10:]
                        last_10_digits_set.add(last_10)
                    else:
                        exact_wa_ids.append(wa_id)
                
                # Add exact matches
                if exact_wa_ids:
                    wa_id_conditions.append(Message.from_wa_id.in_(exact_wa_ids))
                
                # Add last 10 digits matches using LIKE pattern
                if last_10_digits_set:
                    for last_10 in last_10_digits_set:
                        wa_id_conditions.append(Message.from_wa_id.like(f'%{last_10}'))
                
                if wa_id_conditions:
                    reply_conditions.append(or_(*wa_id_conditions))
            
            if reply_conditions:
                replied_messages = db.query(Message.customer_id, Message.from_wa_id).filter(
                    or_(*reply_conditions),
                    Message.sender_type == "customer",
                    Message.timestamp >= campaign_send_time
                ).distinct().all()
                
                for msg_customer_id, msg_wa_id in replied_messages:
                    if msg_customer_id:
                        replied_customer_ids.add(msg_customer_id)
                    if msg_wa_id:
                        # Normalize wa_id to last 10 digits for comparison
                        wa_id_digits = re.sub(r'\D', '', msg_wa_id)
                        if len(wa_id_digits) >= 10:
                            replied_wa_ids.add(wa_id_digits[-10:])
                        else:
                            replied_wa_ids.add(msg_wa_id)
                
                # Count unique: use customer_ids if available, otherwise use wa_ids
                if replied_customer_ids:
                    total_replied = len(replied_customer_ids)
                elif replied_wa_ids:
                    total_replied = len(replied_wa_ids)
        
        # Calculate CTR (Click-Through Rate) - using replied as proxy for clicks
        ctr = (total_replied / total_delivered * 100) if total_delivered > 0 else 0.0
        
        # Calculate ROI (Return on Investment) - simplified calculation
        # ROI = (Revenue - Cost) / Cost * 100
        # For now, we'll use a placeholder calculation based on replies
        # In production, you'd track actual revenue from campaign conversions
        roi = (total_replied * 10) if total_replied > 0 else 0.0  # Placeholder: 10x multiplier
        
        # Determine campaign status
        if latest_job and latest_job.last_triggered_time:
            # Check if campaign is still active (sent within last 30 days and has pending/success statuses)
            thirty_days_ago = datetime.now() - timedelta(days=30)
            if latest_job.last_triggered_time >= thirty_days_ago:
                # Check if there are still pending messages
                pending_count = db.query(JobStatus).filter(
                    JobStatus.job_id.in_(job_ids),
                    JobStatus.status == "pending"
                ).count()
                status = "active" if pending_count > 0 or total_delivered > 0 else "completed"
            else:
                status = "completed"
        else:
            status = "pending"
        
        campaign_list.append({
            "id": str(campaign.id),
            "name": campaign.name,
            "type": campaign.type,
            "description": campaign.description,
            "status": status,
            "sent": total_sent,
            "delivered": total_delivered,
            "read": total_read,
            "replied": total_replied,
            "ctr": round(ctr, 1),
            "roi": round(roi, 1),
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None
        })
    
    return campaign_list