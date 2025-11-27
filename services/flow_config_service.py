from __future__ import annotations

import re
from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select

from models.models import NumberFlowConfig


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
    flow = get_flow_by_id(db, flow_id)
    if not flow:
        raise ValueError("Flow configuration not found")
    flow.is_enabled = bool(is_enabled)
    db.add(flow)
    db.commit()
    db.refresh(flow)
    return flow

