# app.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

import consumer
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
    template_controller, files_controller, job_controller, dashboard_controller
)
from database.db import SessionLocal, engine, get_db
from models import models
from schemas.token_schema import Token
from automation.controller import router as automation_router

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
        # "https://connect.olivaclinic.com",
        # "https://whatsapp.olivaclinic.com",
        # "http://localhost:8080"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/test-this")
def test():
    return {
        "test":"now plese fetch images"
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
# app.include_router(automation_router,prefix="/automation")

app.include_router(zenoti_router, prefix="/zenoti")
app.include_router(cost_router, prefix="/cost")

app.include_router(clients_router)