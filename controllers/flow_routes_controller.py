from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, root_validator
from sqlalchemy.orm import Session

from database.db import get_db
from services import flow_config_service


router = APIRouter(prefix="/flow/routes", tags=["flow-routes"])


class FlowUpdatePayload(BaseModel):
    is_enabled: Optional[bool] = None
    auto_enable_from: Optional[datetime] = None
    auto_enable_to: Optional[datetime] = None
    clear_schedule: bool = False

@root_validator(skip_on_failure=True)
def validate_window(cls, values):
        clear_schedule = values.get("clear_schedule")
        start = values.get("auto_enable_from")
        end = values.get("auto_enable_to")

        if clear_schedule:
            values["auto_enable_from"] = None
            values["auto_enable_to"] = None
            return values

        if (start is None) ^ (end is None):
            raise ValueError("Both auto_enable_from and auto_enable_to must be provided together")
        if start and end and end <= start:
            raise ValueError("auto_enable_to must be after auto_enable_from")
        return values


@router.get("")
def list_flow_routes(db: Session = Depends(get_db)):
    flows = flow_config_service.list_flows(db)
    data = [flow_config_service.serialize_flow(flow) for flow in flows]
    enabled = sum(1 for flow in data if flow.get("is_live_now"))
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
def update_flow_route(flow_id: str, payload: FlowUpdatePayload, db: Session = Depends(get_db)):
    try:
        flow = flow_config_service.update_flow_settings(
            db,
            flow_id,
            is_enabled=payload.is_enabled,
            auto_enable_from=payload.auto_enable_from,
            auto_enable_to=payload.auto_enable_to,
            clear_schedule=payload.clear_schedule,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "success": True,
        "data": flow_config_service.serialize_flow(flow),
    }

