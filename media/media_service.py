import mimetypes

import requests
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import MEDIA_URL
from services import whatsapp_service
from services.whatsapp_service import get_latest_token


def upload_media_file(file: UploadFile, db: Session) -> dict:
    """
    Upload media to WhatsApp Cloud API and return the media ID.
    """
    token_obj = whatsapp_service.get_latest_token(db)
    if not token_obj:
        raise HTTPException(status_code=400, detail="Token not available")

    token = token_obj.token
    mime_type = mimetypes.guess_type(file.filename)[0]
    if not mime_type:
        raise HTTPException(status_code=400, detail="Invalid file type")

    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "file": (file.filename, file.file.read(), mime_type),
        "messaging_product": (None, "whatsapp")
    }

    media_url = MEDIA_URL
    upload_res = requests.post(media_url, headers=headers, files=files)

    if upload_res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Media upload failed: {upload_res.text}")

    media_id = upload_res.json().get("id")
    return {"id": media_id}
