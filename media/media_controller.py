from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from database.db import get_db
from media.media_service import upload_media_file

router = APIRouter(
    tags=["Media"]
)


@router.post("/upload")
def upload_media(
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """
    Upload media to WhatsApp and return the media ID.
    """
    return upload_media_file(file, db)
