"""
Lead metrics and audit logging for admin reporting.

Writes CSV rows to `marketing/lead_metrics.csv` to avoid touching other app layers.
Collects: timestamp, event_type, wa_id, phone, full_name, step, details, meta.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


_METRICS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lead_metrics.csv")
_CSV_HEADER = [
    "timestamp_iso",
    "event_type",
    "wa_id",
    "phone",
    "full_name",
    "step",
    "details",
    "meta_json",
]


def _ensure_file() -> None:
    # Create file and header if missing
    os.makedirs(os.path.dirname(_METRICS_FILE), exist_ok=True)
    if not os.path.exists(_METRICS_FILE):
        with open(_METRICS_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_HEADER)


def infer_step_from_details(details: Optional[Dict[str, Any]]) -> str:
    """Best-effort inference of the user's current step based on known fields."""
    d = details or {}
    # Order matters: later checks represent more progress
    try:
        if d.get("dropoff_point"):
            return f"dropped_{d.get('dropoff_point')}"
    except Exception:
        pass
    try:
        if d.get("selected_time") or d.get("custom_time"):
            return "time_selected"
        if d.get("selected_week") or d.get("custom_date") or d.get("selected_date") or d.get("appointment_date"):
            return "date_selected"
        if d.get("selected_clinic"):
            return "clinic_selected"
        if d.get("selected_location"):
            return "location_selected"
        if d.get("selected_city"):
            return "city_selected"
        if d.get("selected_concern") or d.get("zoho_mapped_concern"):
            return "concern_selected"
    except Exception:
        pass
    return "start"


def log_lead_metric(
    *,
    event_type: str,
    wa_id: Optional[str],
    phone: Optional[str],
    full_name: Optional[str],
    step: Optional[str] = None,
    details: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a metric row to the CSV file.

    event_type: one of ["push_attempt", "push_success", "push_failed",
                        "duplicate_same_day", "termination", "debug"]
    """
    try:
        _ensure_file()
        ts = datetime.utcnow().isoformat()
        row = [
            ts,
            event_type,
            wa_id or "",
            phone or "",
            (full_name or "").strip(),
            (step or "").strip(),
            (details or "").strip(),
            json.dumps(meta or {}, ensure_ascii=False),
        ]
        with open(_METRICS_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception:
        # Intentionally swallow logging errors
        pass


