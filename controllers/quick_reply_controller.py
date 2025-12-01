from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database.db import get_db
from models.models import User
from schemas.quick_reply_schema import (
    QuickReplyCreate,
    QuickReplyListResponse,
    QuickReplyOut,
)
from services.quick_reply_service import (
    create_quick_reply,
    delete_quick_reply,
    list_quick_replies,
)

router = APIRouter(prefix="/quick-replies", tags=["Quick Replies"])


@router.get("/", response_model=QuickReplyListResponse)
def fetch_quick_replies(category: str | None = None, db: Session = Depends(get_db)):
    items = list_quick_replies(db, category=category)
    return {"items": items, "total": len(items)}


@router.post("/", response_model=QuickReplyOut, status_code=status.HTTP_201_CREATED)
def create_quick_reply_endpoint(
    payload: QuickReplyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_quick_reply(db, payload, current_user.id if current_user else None)


@router.delete("/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quick_reply_endpoint(
    reply_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = delete_quick_reply(db, reply_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Quick reply not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


