from __future__ import annotations

# Central wiring for marketing treatment-related flows.
# This module re-exports the public functions used by the websocket layer,
# so callers import from a single stable path: `marketing.flows`.

from sqlalchemy.orm import Session  # noqa: F401 (type export)

# Re-export treatment flows
from .treament_flow import (
    run_treament_flow,
    run_treatment_buttons_flow,
    run_book_appointment_flow,
    run_confirm_appointment_flow,
)

__all__ = [
    "run_treament_flow",
    "run_treatment_buttons_flow",
    "run_book_appointment_flow",
    "run_confirm_appointment_flow",
]


