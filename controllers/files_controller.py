import mimetypes
import os
from io import BytesIO
from typing import List

import httpx
from fastapi import UploadFile, File, HTTPException, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import requests
from starlette.responses import StreamingResponse

from database.db import get_db
from schemas.file_schema import FileResponse
from services import whatsapp_service, file_service

router = APIRouter(tags=["Files"])

META_UPLOAD_URL = f"https://graph.facebook.com/v22.0/367633743092037/media"

@router.post("/upload")
async def upload_to_meta(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        # 🔐 Get token from DB
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise HTTPException(status_code=400, detail="Token not available")

        token = token_obj.token
        headers = {
            "Authorization": f"Bearer {token}"
        }

        # ✅ Read file content once
        file_bytes = await file.read()

        # ✅ Use MIME type fallback
        mime_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

        # ✅ Exactly match cURL structure: 'messaging_product' as form field, 'file' as file field
        files = {
            "messaging_product": (None, "whatsapp"),
            "file": (file.filename, file_bytes, mime_type)
        }

        # ✅ Send request
        response = requests.post(META_UPLOAD_URL, headers=headers, files=files)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Media upload failed: {response.text}")

        meta_response = response.json()
        media_id = meta_response["id"]

        file_service.create_file_record(
            db=db,
            file_id=media_id,
            name=file.filename,
            mimetype=mime_type
        )
        return response.json()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"500: {str(e)}")

API_VERSION = "v22.0"
META_MEDIA_URL = f"https://graph.facebook.com/{API_VERSION}"

@router.get("/{media_id}")
def get_image(media_id: str, db: Session = Depends(get_db)):
    # 1. Get the latest access token
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Fetch media URL using media_id
    metadata_url = f"https://graph.facebook.com/v23.0/{media_id}"
    meta_res = requests.get(metadata_url, headers=headers)

    if meta_res.status_code != 200:
        raise HTTPException(status_code=meta_res.status_code, detail="Failed to fetch media metadata")

    media_url = meta_res.json().get("url")
    if not media_url:
        raise HTTPException(status_code=400, detail="Media URL not found")

    # 3. Fetch the actual media file from media URL
    media_res = requests.get(media_url, headers=headers, stream=True)
    if media_res.status_code != 200:
        raise HTTPException(status_code=media_res.status_code, detail="Failed to download media")

    content_type = media_res.headers.get("Content-Type", "application/octet-stream")

    # 4. Return the media as a streamed response
    return StreamingResponse(media_res.raw, media_type=content_type)

@router.get("/", response_model=List[FileResponse])
def list_files(db: Session = Depends(get_db)):
    return file_service.get_all_files(db)