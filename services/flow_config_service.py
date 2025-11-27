from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from models.models import NumberFlowConfig

IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET)


def _normalize_digits(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    return digits[-10:] if len(digits) >= 10 else digits


def list_flows(db: Session) -> Sequence[NumberFlowConfig]:
    return (
        db.execute(
            select(NumberFlowConfig).order_by(NumberFlowConfig.priority.asc(), NumberFlowConfig.flow_name.asc())
        )
        .scalars()
        .all()
    )


def _now_utc() -> datetime:
    return datetime.utcnow()


def _normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    # Treat naive datetimes as IST inputs and convert to UTC
    return value - IST_OFFSET


def _to_ist(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone(IST_TZ)


def compute_effective_state(flow: NumberFlowConfig, now: Optional[datetime] = None) -> Tuple[bool, bool]:
    """
    Returns (is_live_now, auto_window_active)
    """
    now = now or _now_utc()
    auto_active = False
    if flow.auto_enable_from and flow.auto_enable_to:
        auto_active = flow.auto_enable_from <= now <= flow.auto_enable_to
    is_live = bool(flow.is_enabled or auto_active)
    return is_live, auto_active


def get_flow_by_id(db: Session, flow_id: str) -> Optional[NumberFlowConfig]:
    if not flow_id:
        return None
    return db.get(NumberFlowConfig, flow_id)


def get_flow_for_incoming(
    db: Session,
    *,
    phone_number_id: Optional[str],
    display_number: Optional[str],
) -> Optional[NumberFlowConfig]:
    phone_number_id = str(phone_number_id).strip() if phone_number_id else None
    if phone_number_id:
        flow = (
            db.execute(select(NumberFlowConfig).where(NumberFlowConfig.phone_number_id == phone_number_id))
            .scalars()
            .first()
        )
        if flow:
            return flow

    digits = _normalize_digits(display_number)
    if digits:
        return (
            db.execute(select(NumberFlowConfig).where(NumberFlowConfig.display_digits == digits))
            .scalars()
            .first()
        )
    return None


def update_flow_status(db: Session, flow_id: str, *, is_enabled: bool) -> NumberFlowConfig:
    return update_flow_settings(db, flow_id, is_enabled=is_enabled)


def update_flow_settings(
    db: Session,
    flow_id: str,
    *,
    is_enabled: Optional[bool] = None,
    auto_enable_from: Optional[datetime] = None,
    auto_enable_to: Optional[datetime] = None,
    clear_schedule: bool = False,
) -> NumberFlowConfig:
    flow = get_flow_by_id(db, flow_id)
    if not flow:
        raise ValueError("Flow configuration not found")

    if is_enabled is not None:
        flow.is_enabled = bool(is_enabled)

    if clear_schedule:
        flow.auto_enable_from = None
        flow.auto_enable_to = None
    else:
        if auto_enable_from is not None:
            flow.auto_enable_from = _normalize_dt(auto_enable_from)
        if auto_enable_to is not None:
            flow.auto_enable_to = _normalize_dt(auto_enable_to)

        # Ensure both are present or both cleared together
        if (flow.auto_enable_from and not flow.auto_enable_to) or (flow.auto_enable_to and not flow.auto_enable_from):
            raise ValueError("Both auto_enable_from and auto_enable_to must be provided together")
        if flow.auto_enable_from and flow.auto_enable_to and flow.auto_enable_to <= flow.auto_enable_from:
            raise ValueError("auto_enable_to must be greater than auto_enable_from")

    db.add(flow)
    db.commit()
    db.refresh(flow)
    return flow


def serialize_flow(flow: NumberFlowConfig) -> dict:
    is_live, auto_active = compute_effective_state(flow)
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
        "is_live_now": is_live,
        "auto_window_active": auto_active,
        "auto_enable_from": flow.auto_enable_from.isoformat() if flow.auto_enable_from else None,
        "auto_enable_to": flow.auto_enable_to.isoformat() if flow.auto_enable_to else None,
        "auto_enable_from_ist": _to_ist(flow.auto_enable_from).isoformat() if flow.auto_enable_from else None,
        "auto_enable_to_ist": _to_ist(flow.auto_enable_to).isoformat() if flow.auto_enable_to else None,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "created_at_ist": _to_ist(flow.created_at).isoformat() if flow.created_at else None,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
        "updated_at_ist": _to_ist(flow.updated_at).isoformat() if flow.updated_at else None,
    }

