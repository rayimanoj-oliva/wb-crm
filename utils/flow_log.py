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
    response_json: Optional[str] = None,
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
            response_json=response_json,
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


def log_last_step_reached(
    db: Session,
    *,
    flow_type: str,
    step: str,
    wa_id: Optional[str] = None,
    name: Optional[str] = None,
) -> str:
    """Log the last step reached in a flow before follow-ups.
    
    Steps for lead_appointment flow:
    - entry: Flow started (auto_welcome sent)
    - city_selection: City selection list shown
    - treatment: Treatment/concern selected
    - concern_list: Concern list shown (if applicable)
    - last_step: Final step before follow-ups (time slot selection or callback confirmation)
    
    Returns the created FlowLog id (as str) if successful, else empty string.
    """
    try:
        log = FlowLog(
            flow_type=flow_type,
            step=step,
            status_code=None,
            wa_id=wa_id,
            name=name,
            description=f"Last step reached: {step}",
            response_json=None,
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
