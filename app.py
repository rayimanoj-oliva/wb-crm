# app.py
import logging
import sys
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import timedelta
from controllers import ws_channel
import consumer

# Configure logging to ensure messages appear in server logs
# This must be done BEFORE any other imports that create loggers
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Explicitly use stdout
    ],
    force=True  # Override any existing configuration
)

# Ensure root logger is at INFO level
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Ensure stdout is unbuffered
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# Create logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Silence noisy follow-up scheduler logs (set to WARNING to only show important messages)
logging.getLogger("followup_scheduler").setLevel(logging.WARNING)
logging.getLogger("followup_service").setLevel(logging.WARNING)

# Enable uvicorn access logs to see API requests
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

# Silence other noisy loggers
logging.getLogger("passlib").setLevel(logging.WARNING)
from media import media_controller
from zenoti.zenoti_controller import router as zenoti_router
from starlette.middleware.cors import CORSMiddleware
from clients.controller import router as clients_router
from controllers.cost_controller import router as cost_router


from auth import authenticate_user, create_access_token
from controllers import (
    user_controller,
    auth_controller,
    customer_controller,
    web_hook, web_socket, messages_controller, whatsapp_controller, order_controller, campaign_controller,
    template_controller, files_controller, job_controller, dashboard_controller, referrer_controller
)
from controllers.payment_controller import router as payment_router
from controllers.webhook_controller import router as webhook_router, router2 as webhook2_router

from controllers.address_controller import router as address_router
from controllers.catalog import router as catalog_router
from controllers.catalog import seed_categories, seed_subcategories
from seed_zoho_mappings import seed_zoho_mappings
from flow_integration import router as flow_router
from controllers.flow_routes_controller import router as flow_routes_router
from controllers.components.lead_appointment_flow.zoho_lead_api import router as zoho_leads_router
from controllers.components.zoho_mapping_controller import router as zoho_mapping_router
from controllers.followup_debug_controller import router as followup_debug_router
from controllers.flow_logs_controller import router as flow_logs_router
from controllers.analytics_controller import router as analytics_router
from controllers.quick_reply_controller import router as quick_reply_router
from controllers.organization_controller import router as organization_router
from controllers.whatsapp_number_controller import router as whatsapp_number_router
from controllers.role_controller import router as role_router
from database.db import SessionLocal, engine, get_db
from models import models
from schemas.token_schema import Token
from automation.controller import router as automation_router
import asyncio
from datetime import datetime, timedelta
from services.followup_service import due_customers_for_followup, FOLLOW_UP_2_TEXT, send_followup1_interactive, send_followup2
from utils.whatsapp import send_message_to_waid


models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
        #  "https://connect.olivaclinic.com",
        #  "https://whatsapp.olivaclinic.com",
        # "http://localhost:8080"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/test-this")
def test():
    return {
        "test":"now please fetch images"
    }
@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    # Extend session timeout to 8 hours to honor "no auto logout" requirement
    token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(hours=8))
    return {"access_token": token, "token_type": "bearer"}

# Include user routes
app.include_router(user_controller.router, prefix="/user")
app.include_router(auth_controller.router, prefix="/auth")
app.include_router(customer_controller.router, prefix="/customer")
app.include_router(web_hook.router, prefix="/wh")
app.include_router(ws_channel.router, prefix="/ws")
app.include_router(messages_controller.router, prefix="/message")
app.include_router(whatsapp_controller.router,prefix="/secret")
app.include_router(order_controller.router,prefix="/orders")
app.include_router(campaign_controller.router, prefix="/campaign")
app.include_router(template_controller.router, prefix="/templates")
app.include_router(files_controller.router, prefix="/files")
app.include_router(job_controller.router, prefix="/job")
app.include_router(dashboard_controller.router, prefix="/dashboard")
app.include_router(referrer_controller.router)
# app.include_router(automation_router,prefix="/automation")
app.include_router(clients_router, prefix="/client")
app.include_router(zenoti_router, prefix="/zenoti")
app.include_router(cost_router, prefix="/cost")
app.include_router(media_controller.router, prefix="/media")
app.include_router(payment_router, prefix="/payments")
# app.include_router(address_router, prefix="/address")
app.include_router(catalog_router, prefix="/catalog")
app.include_router(flow_router, prefix="/flow")
app.include_router(flow_routes_router)
app.include_router(zoho_leads_router)
app.include_router(zoho_mapping_router, prefix="/zoho-mappings")
app.include_router(followup_debug_router)  # Debug endpoints for follow-ups
app.include_router(flow_logs_router)  # Flow logs API
app.include_router(analytics_router)  # Analytics API
app.include_router(quick_reply_router)
app.include_router(organization_router)  # Organizations API
app.include_router(whatsapp_number_router)  # WhatsApp Numbers API
app.include_router(role_router)  # Roles API
app.include_router(webhook_router)  # First webhook endpoint: POST/GET /webhook
app.include_router(webhook2_router)  # Second webhook endpoint: POST/GET /webhook2



@app.on_event("startup")
def seed_catalog_on_startup():
    db = SessionLocal()
    try:
        seed_categories(db)
        seed_subcategories(db)
        seed_zoho_mappings()
    finally:
        db.close()


@app.on_event("startup")
async def start_followup_scheduler():
    """Start the follow-up scheduler with distributed locking support."""
    from services.followup_service import acquire_followup_lock, release_followup_lock
    
    async def _runner():
        scheduler_logger = logging.getLogger("followup_scheduler")
        iteration = 0
        while True:
            db = None
            try:
                iteration += 1
                # Only log every 100 iterations to reduce noise
                if iteration % 100 == 1:
                    scheduler_logger.info(f"Follow-up scheduler running (iteration {iteration})")
                
                db = SessionLocal()
                customers = due_customers_for_followup(db)
                
                if customers:
                    scheduler_logger.info(f"Found {len(customers)} customer(s) due for follow-up")
                # No need to log when no customers are due - reduces noise
                
                for c in customers:
                    lock_value = None
                    try:
                        # Acquire distributed lock to prevent duplicate processing
                        lock_value = acquire_followup_lock(str(c.id))
                        if lock_value is None:
                            scheduler_logger.info(f"Skipping customer {c.id} (wa_id: {c.wa_id}) - already being processed")
                            continue
                        
                        scheduler_logger.info(f"Processing follow-up for customer {c.id} (wa_id: {c.wa_id})")
                        
                        # Decide which follow-up to send based on last_message_type
                        if (c.last_message_type or "").lower() == "follow_up_1_sent":
                            # Only send Follow-Up 2 if NO replies since Follow-Up 1
                            # infer follow-up 1 sent time as next_followup_time - FOLLOW_UP_2_DELAY_MINUTES
                            from services.followup_service import FOLLOW_UP_2_DELAY_MINUTES
                            fu1_sent_at = (c.next_followup_time - timedelta(minutes=FOLLOW_UP_2_DELAY_MINUTES)) if c.next_followup_time else None
                            if fu1_sent_at and c.last_interaction_time and c.last_interaction_time >= fu1_sent_at:
                                # user replied after Follow-Up 1; skip Follow-Up 2
                                c.next_followup_time = None
                                db.add(c)
                                db.commit()
                                scheduler_logger.info(f"Customer {c.wa_id} replied after Follow-Up 1, skipping Follow-Up 2")
                                continue
                            
                            # Send Follow-Up 2 and create a lead with available details
                            await send_followup2(db, wa_id=c.wa_id)
                            
                            # Create lead with available details
                            try:
                                from services import customer_service
                                customer = customer_service.get_customer_record_by_wa_id(db, c.wa_id)
                            except Exception as e:
                                scheduler_logger.warning(f"Could not get customer record: {e}")
                                customer = c
                            
                            try:
                                from controllers.components.lead_appointment_flow.zoho_integration import trigger_zoho_lead_creation
                                await trigger_zoho_lead_creation(db, wa_id=c.wa_id, customer=customer, lead_status="CALL_INITIATED")
                            except Exception as e:
                                scheduler_logger.warning(f"Could not create Zoho lead: {e}")
                        else:
                            # Before sending Follow-Up 1, double-check that user hasn't replied recently
                            # This ensures we only send if 2 minutes have truly passed since last interaction
                            from services.followup_service import FOLLOW_UP_1_DELAY_MINUTES
                            db.refresh(c)  # Refresh to get latest state
                            
                            if c.last_interaction_time:
                                time_since_last_interaction = (datetime.utcnow() - c.last_interaction_time).total_seconds() / 60
                                if time_since_last_interaction < FOLLOW_UP_1_DELAY_MINUTES:
                                    # User interacted less than 2 minutes ago, skip this follow-up
                                    scheduler_logger.info(f"Skipping Follow-Up 1 for customer {c.wa_id} - user interacted {time_since_last_interaction:.1f} minutes ago (less than {FOLLOW_UP_1_DELAY_MINUTES} min)")
                                    c.next_followup_time = None
                                    db.add(c)
                                    db.commit()
                                    continue
                            
                            # Send Follow-Up 1 (interactive Yes/No) and schedule Follow-Up 2
                            await send_followup1_interactive(db, wa_id=c.wa_id)
                            # send_followup1_interactive already schedules Follow-Up 2 and sets label
                        
                        db.add(c)
                        db.commit()
                        scheduler_logger.info(f"Successfully processed follow-up for customer {c.wa_id}")
                        
                    except Exception as e:
                        scheduler_logger.error(f"Failed to process follow-up for customer {c.id if c else 'unknown'}: {e}", exc_info=True)
                        if db:
                            db.rollback()
                    finally:
                        # Always release the lock
                        if lock_value and c:
                            release_followup_lock(str(c.id), lock_value)
                
                if db:
                    db.close()
                    db = None
                
                # Wait 30 seconds before next iteration
                await asyncio.sleep(30)
                
            except Exception as e:
                scheduler_logger.error(f"Critical error in scheduler: {e}", exc_info=True)
                if db:
                    try:
                        db.close()
                    except:
                        pass
                    db = None
                # Wait before retrying after error
                await asyncio.sleep(30)

    # Start follow-up scheduler silently
    asyncio.create_task(_runner())

