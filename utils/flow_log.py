from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
import uuid as _uuid

from sqlalchemy.orm import Session

from models.models import FlowLog


def log_flow_event(
    db: Session,
    *,
    flow_type: str,
    step: Optional[str] = None,
    status_code: Optional[int] = None,
    wa_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Persist a flow log entry. Swallows DB errors to avoid impacting user flows.

    Returns the created FlowLog id (as str) if successful, else empty string.
    """
    try:
        log = FlowLog(
            flow_type=flow_type,
            step=step,
            status_code=status_code,
            wa_id=wa_id,
            name=name,
            description=description,
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
        return str(log.id)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return ""

