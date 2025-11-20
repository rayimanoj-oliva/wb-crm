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


def _get_customer_name_from_flow_state(db: Session, wa_id: Optional[str], flow_type: str) -> Optional[str]:
    """Get customer name from flow state based on flow type.
    
    For lead_appointment flow: Check lead_appointment_state first, then customer record
    For treatment flow: Check appointment_state first, then customer record
    
    Returns the name if found, else None.
    """
    if not wa_id:
        return None
    
    try:
        if flow_type == "lead_appointment":
            # Try to get name from lead_appointment_state first
            try:
                from controllers.web_socket import lead_appointment_state  # type: ignore
                state = lead_appointment_state.get(wa_id, {})
                user_name = state.get("user_name")
                if user_name:
                    return str(user_name).strip()
            except Exception:
                pass
        elif flow_type == "treatment":
            # Try to get name from appointment_state first
            try:
                from controllers.web_socket import appointment_state  # type: ignore
                state = appointment_state.get(wa_id, {})
                user_name = state.get("user_name")
                if user_name:
                    return str(user_name).strip()
            except Exception:
                pass
        
        # Fallback: Get from customer record
        try:
            from services.customer_service import get_customer_record_by_wa_id
            customer = get_customer_record_by_wa_id(db, wa_id)
            if customer and hasattr(customer, 'name') and customer.name:
                return str(customer.name).strip()
        except Exception:
            pass
    except Exception:
        pass
    
    return None


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
    
    If name is not provided, it will be retrieved from the appropriate flow state.
    
    Returns the created FlowLog id (as str) if successful, else empty string.
    """
    try:
        # If name not provided, try to get it from flow state
        if not name:
            name = _get_customer_name_from_flow_state(db, wa_id, flow_type)
        
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