# app.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

import consumer
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

from controllers.address_controller import router as address_router
from controllers.catalog import router as catalog_router
from controllers.catalog import seed_categories, seed_subcategories
from seed_zoho_mappings import seed_zoho_mappings
from flow_integration import router as flow_router
from controllers.components.lead_appointment_flow.zoho_lead_api import router as zoho_leads_router
from controllers.components.zoho_mapping_controller import router as zoho_mapping_router
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
    token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(minutes=30))
    return {"access_token": token, "token_type": "bearer"}

# Include user routes
app.include_router(user_controller.router, prefix="/user")
app.include_router(auth_controller.router, prefix="/auth")
app.include_router(customer_controller.router, prefix="/customer")
app.include_router(web_hook.router, prefix="/wh")
app.include_router(web_socket.router, prefix="/ws")
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
app.include_router(zoho_leads_router)
app.include_router(zoho_mapping_router, prefix="/zoho-mappings")



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
    async def _runner():
        while True:
            db = SessionLocal()
            try:
                customers = due_customers_for_followup(db)
                for c in customers:
                    try:
                        # Decide which follow-up to send based on last_message_type
                        if (c.last_message_type or "").lower() == "follow_up_1_sent":
                            # Only send Follow-Up 2 if NO replies since Follow-Up 1
                            # infer follow-up 1 sent time as next_followup_time - 5 minutes
                            fu1_sent_at = (c.next_followup_time - timedelta(minutes=5)) if c.next_followup_time else None
                            if fu1_sent_at and c.last_interaction_time and c.last_interaction_time >= fu1_sent_at:
                                # user replied after Follow-Up 1; skip Follow-Up 2
                                c.next_followup_time = None
                                db.add(c)
                                db.commit()
                                continue
                            # Send Follow-Up 2 and create a lead with available details
                            await send_followup2(db, wa_id=c.wa_id)
                            # Create lead with available details
                            try:
                                from services import customer_service
                                customer = customer_service.get_customer_record_by_wa_id(db, c.wa_id)
                            except Exception:
                                customer = c
                            try:
                                from controllers.components.lead_appointment_flow.zoho_integration import trigger_zoho_lead_creation
                                await trigger_zoho_lead_creation(db, wa_id=c.wa_id, customer=customer, lead_status="CALL_INITIATED")
                            except Exception:
                                pass
                        else:
                            # Send Follow-Up 1 (interactive Yes/No) and schedule Follow-Up 2 in 5 minutes
                            await send_followup1_interactive(db, wa_id=c.wa_id)
                            # send_followup1_interactive already schedules 5 minutes and sets label
                        db.add(c)
                        db.commit()
                    except Exception:
                        db.rollback()
                        pass
            finally:
                db.close()
            await asyncio.sleep(30)

    asyncio.create_task(_runner())

