from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import get_db
from services import flow_config_service
from models.models import NumberFlowConfig


router = APIRouter(prefix="/flow/routes", tags=["flow-routes"])


class FlowTogglePayload(BaseModel):
    is_enabled: bool


def _serialize(flow: NumberFlowConfig) -> Dict[str, Any]:
    return {
        "id": str(flow.id),
        "phone_number_id": flow.phone_number_id,
        "display_number": flow.display_number,
        "display_digits": flow.display_digits,
        "flow_key": flow.flow_key,
        "flow_name": flow.flow_name,
        "description": flow.description,
        "priority": flow.priority,
        "is_enabled": bool(flow.is_enabled),
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
    }


@router.get("")
def list_flow_routes(db: Session = Depends(get_db)):
    flows = flow_config_service.list_flows(db)
    data = [_serialize(flow) for flow in flows]
    enabled = sum(1 for flow in flows if flow.is_enabled)
    total = len(flows)
    return {
        "success": True,
        "data": data,
        "counts": {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
        },
    }


@router.patch("/{flow_id}")
def update_flow_route(flow_id: str, payload: FlowTogglePayload, db: Session = Depends(get_db)):
    try:
        flow = flow_config_service.update_flow_status(db, flow_id, is_enabled=payload.is_enabled)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "success": True,
        "data": _serialize(flow),
    }

