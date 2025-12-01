from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from models.models import QuickReply
from schemas.quick_reply_schema import QuickReplyCreate, QuickReplyUpdate


def list_quick_replies(db: Session, category: Optional[str] = None) -> List[QuickReply]:
    query = db.query(QuickReply)
    if category:
        query = query.filter(QuickReply.category == category)
    return (
        query.order_by(QuickReply.category.asc().nullsfirst(), QuickReply.title.asc()).all()
    )


def create_quick_reply(db: Session, payload: QuickReplyCreate, creator_id: Optional[UUID]) -> QuickReply:
    quick_reply = QuickReply(
        title=payload.title.strip(),
        content=payload.content.strip(),
        category=(payload.category or "").strip() or None,
        created_by=creator_id,
    )
    db.add(quick_reply)
    db.commit()
    db.refresh(quick_reply)
    return quick_reply


def update_quick_reply(db: Session, reply_id: UUID, payload: QuickReplyUpdate) -> Optional[QuickReply]:
    quick_reply = db.query(QuickReply).filter(QuickReply.id == reply_id).first()
    if not quick_reply:
        return None

    if payload.title is not None:
        quick_reply.title = payload.title.strip()
    if payload.content is not None:
        quick_reply.content = payload.content.strip()
    if payload.category is not None:
        quick_reply.category = payload.category.strip() or None

    db.commit()
    db.refresh(quick_reply)
    return quick_reply


def delete_quick_reply(db: Session, reply_id: UUID) -> bool:
    quick_reply = db.query(QuickReply).filter(QuickReply.id == reply_id).first()
    if not quick_reply:
        return False

    db.delete(quick_reply)
    db.commit()
    return True


