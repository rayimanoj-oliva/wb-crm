from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(
    tags=["Webhook"]
)

@router.post("/")
async def echo_body(request: Request):
    body = await request.json()
    return JSONResponse(content=body)
