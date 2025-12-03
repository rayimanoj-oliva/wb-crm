
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.params import Depends
from sqlalchemy.orm import Session
import requests

from database.db import get_db
from schemas.template_schema import TemplatesResponse, CreateMetaTemplateRequest, TemplateStructure
from models.models import Template
from services.template_service import (
    get_all_templates_from_meta,
    create_template_on_meta,
    send_template_to_facebook,
    delete_template_from_meta,
)
from services.whatsapp_service import get_latest_token

router = APIRouter(tags=["Templates"])
@router.get("/meta", response_model=TemplatesResponse)
def fetch_meta_templates(db: Session = Depends(get_db)):
    return get_all_templates_from_meta(db)


@router.post("/")
def create_template(template: TemplateStructure, db: Session = Depends(get_db)):
    try:
        response = send_template_to_facebook(template.root, db)
        return {"status": "success", "facebook_response": response}
    except HTTPException:
        # Re-raise HTTPException to preserve status code and detail
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.delete("/")
def delete_template(template_name: str, db: Session = Depends(get_db)):
    try:
        result = delete_template_from_meta(template_name, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Removed explicit sync endpoint; templates are persisted automatically when fetched/created/deleted


@router.get("/local")
def list_local_templates(db: Session = Depends(get_db)):
    items = db.query(Template).all()
    return items


@router.post("/upload-header-image")
async def upload_header_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload an image for use in template headers using Facebook's Resumable Upload API.

    This returns a valid media handle that can be used in template creation.
    The media handle expires quickly, so create the template immediately after uploading.
    """
    token_entry = get_latest_token(db)
    if not token_entry:
        raise HTTPException(status_code=404, detail="WhatsApp token not found")

    token = token_entry.token

    # Read file content
    content = await file.read()
    content_type = file.content_type or "image/jpeg"
    filename = file.filename or "header_image.jpg"

    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png"]
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )

    # Validate file size (max 5MB for WhatsApp)
    max_size = 5 * 1024 * 1024  # 5MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 5MB."
        )

    # Get App ID from token debug endpoint
    debug_url = "https://graph.facebook.com/v22.0/debug_token"
    debug_params = {"input_token": token, "access_token": token}
    debug_response = requests.get(debug_url, params=debug_params)

    if debug_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to validate token")

    debug_data = debug_response.json()
    app_id = debug_data.get("data", {}).get("app_id")

    if not app_id:
        raise HTTPException(status_code=500, detail="Could not determine App ID from token")

    # Step 1: Create upload session using Resumable Upload API
    session_url = f"https://graph.facebook.com/v22.0/{app_id}/uploads"
    session_params = {
        "file_name": filename,
        "file_length": len(content),
        "file_type": content_type,
        "access_token": token
    }

    session_response = requests.post(session_url, params=session_params)

    if session_response.status_code != 200:
        raise HTTPException(
            status_code=session_response.status_code,
            detail=f"Failed to create upload session: {session_response.text}"
        )

    session_data = session_response.json()
    upload_session_id = session_data.get("id")

    if not upload_session_id:
        raise HTTPException(status_code=500, detail="Failed to get upload session ID")

    # Step 2: Upload the actual file data
    upload_url = f"https://graph.facebook.com/v22.0/{upload_session_id}"
    headers = {
        "Authorization": f"OAuth {token}",
        "file_offset": "0"
    }

    upload_response = requests.post(upload_url, headers=headers, data=content)

    if upload_response.status_code != 200:
        raise HTTPException(
            status_code=upload_response.status_code,
            detail=f"Failed to upload file: {upload_response.text}"
        )

    upload_data = upload_response.json()
    media_handle = upload_data.get("h")  # Resumable API returns handle in "h" field

    if not media_handle:
        raise HTTPException(status_code=500, detail="Failed to get media handle from upload")

    return {
        "status": "success",
        "media_id": media_handle,
        "message": "Image uploaded successfully. Use this media_id in header_handle array immediately - it expires quickly!",
        "usage": {
            "component_type": "HEADER",
            "format": "IMAGE",
            "example": {
                "header_handle": [media_handle]
            }
        }
    }