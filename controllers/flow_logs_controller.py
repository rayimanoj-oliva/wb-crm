from datetime import datetime
from typing import Optional, Any, Dict, List, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
import csv
import io

from database.db import get_db
from models.models import FlowLog

router = APIRouter(prefix="/api/flow-logs", tags=["flow-logs"])


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        # Accept "YYYY-MM-DD" or ISO strings
        if len(val) == 10:
            return datetime.strptime(val, "%Y-%m-%d")
        return datetime.fromisoformat(val)
    except Exception:
        return None


@router.get("")
def list_flow_logs(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query(None),
    wa_id: Optional[str] = Query(None),
    step: Optional[str] = Query(None),
    status_code: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    q: Optional[str] = Query(None, description="search in description"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        filters = []
        if flow_type:
            filters.append(FlowLog.flow_type == flow_type)
        if wa_id:
            filters.append(FlowLog.wa_id == wa_id)
        if step:
            filters.append(FlowLog.step == step)
        if status_code is not None:
            filters.append(FlowLog.status_code == status_code)
        if date_from:
            dt_from = _parse_dt(date_from)
            if dt_from:
                filters.append(FlowLog.created_at >= dt_from)
        if date_to:
            dt_to = _parse_dt(date_to)
            if dt_to:
                filters.append(FlowLog.created_at <= dt_to)

        query = db.query(FlowLog).filter(and_(*filters)) if filters else db.query(FlowLog)
        if q:
            like = f"%{q}%"
            query = query.filter(FlowLog.description.ilike(like))

        total = query.count()
        rows = (
            query.order_by(FlowLog.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        def _row_to_dict(x: FlowLog) -> Dict[str, Any]:
            return {
                "id": str(x.id),
                "created_at": x.created_at.isoformat() if x.created_at else None,
                "flow_type": x.flow_type,
                "name": x.name,
                "step": x.step,
                "status_code": x.status_code,
                "wa_id": x.wa_id,
                "description": x.description,
                "response_json": x.response_json,
            }

        return {
            "success": True,
            "total": total,
            "page": page,
            "limit": limit,
            "data": [_row_to_dict(r) for r in rows],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
def export_flow_logs_csv(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    try:
        filters = []
        if flow_type:
            filters.append(FlowLog.flow_type == flow_type)
        if date_from:
            dt_from = _parse_dt(date_from)
            if dt_from:
                filters.append(FlowLog.created_at >= dt_from)
        if date_to:
            dt_to = _parse_dt(date_to)
            if dt_to:
                filters.append(FlowLog.created_at <= dt_to)

        query = db.query(FlowLog).filter(and_(*filters)) if filters else db.query(FlowLog)
        rows = query.order_by(FlowLog.created_at.desc()).limit(5000).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["created_at", "wa_id", "name", "flow_type", "step", "status_code", "description"])
        for r in rows:
            writer.writerow([
                r.created_at.isoformat() if r.created_at else "",
                r.wa_id or "",
                r.name or "",
                r.flow_type or "",
                r.step or "",
                r.status_code or "",
                (r.description or "").replace("\n", " "),
            ])
        output.seek(0)

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=flow_logs.csv"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
def flow_summary(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query(None),
    hours: Optional[int] = Query(24, ge=1, le=168, description="Lookback window"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Return one line per wa_id indicating overall flow status.
    Columns: wa_id, status, error_code, error_message, issue_description, last_step, last_at
    Rules:
      - success: has a 'result' step with event_type transition/info and no later error
      - failure: has any error; report latest error_code/message/description
      - pending: otherwise; report the last_step reached
    """
    try:
        filters = []
        if flow_type:
            filters.append(FlowLog.flow_type == flow_type)

        if date_from:
            dt_from = _parse_dt(date_from)
            if dt_from:
                filters.append(FlowLog.created_at >= dt_from)
        if date_to:
            dt_to = _parse_dt(date_to)
            if dt_to:
                filters.append(FlowLog.created_at <= dt_to)
        if not date_from and not date_to and hours:
            # default lookback by hours
            from datetime import timedelta
            since = datetime.utcnow() - timedelta(hours=hours)
            filters.append(FlowLog.created_at >= since)

        query = db.query(FlowLog).filter(and_(*filters)) if filters else db.query(FlowLog)
        rows: List[FlowLog] = query.order_by(FlowLog.wa_id.asc(), FlowLog.created_at.asc()).all()

        # Group by wa_id
        groups: Dict[str, List[FlowLog]] = {}
        for r in rows:
            key = r.wa_id or "unknown"
            groups.setdefault(key, []).append(r)

        result = []
        for wa_id, logs in groups.items():
            last_error: Optional[FlowLog] = None
            last_result: Optional[FlowLog] = None
            last_log: Optional[FlowLog] = logs[-1] if logs else None

            for r in logs:
                if r.status_code and int(r.status_code) >= 400:
                    last_error = r
                if (r.step or "").lower() == "result" and (r.status_code or 0) == 200:
                    last_result = r

            if last_error and (not last_result or last_error.created_at >= last_result.created_at):
                status = "failure"
                error_code = last_error.status_code
                error_message = "ERROR"
                issue_description = last_error.description or ""
                last_step = last_error.step or ""
                last_at = last_error.created_at.isoformat() if last_error.created_at else None
            elif last_result:
                status = "success"
                error_code = 200
                error_message = "OK"
                issue_description = last_result.description or "Flow completed successfully"
                last_step = last_result.step or "result"
                last_at = last_result.created_at.isoformat() if last_result.created_at else None
            else:
                status = "pending"
                error_code = None
                error_message = ""
                issue_description = f"Stopped at step '{(last_log.step if last_log else '')}'" if last_log and last_log.step else "No logs in window"
                last_step = (last_log.step if last_log else "") or ""
                last_at = last_log.created_at.isoformat() if (last_log and last_log.created_at) else None

            result.append({
                "wa_id": wa_id,
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
                "issue_description": issue_description,
                "last_step": last_step,
                "last_at": last_at,
            })

        return {
            "success": True,
            "rows": result,
            "count": len(result),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/completion-counts")
def get_completion_counts(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Get counts of customers who completed full flows (reached 'thank you' stage).
    A flow is considered completed if any log description contains a thank-you message.
    If the flow only has follow-up messages (and no thank-you), it is counted as non-completed.
    """
    try:
        filters = []
        if date_from:
            dt_from = _parse_dt(date_from)
            if dt_from:
                filters.append(FlowLog.created_at >= dt_from)
        if date_to:
            dt_to = _parse_dt(date_to)
            if dt_to:
                filters.append(FlowLog.created_at <= dt_to)

        query = db.query(FlowLog).filter(and_(*filters)) if filters else db.query(FlowLog)
        rows: List[FlowLog] = query.order_by(FlowLog.wa_id.asc(), FlowLog.created_at.asc()).all()

        treatment_groups: Dict[str, List[FlowLog]] = {}
        lead_appointment_groups: Dict[str, List[FlowLog]] = {}

        for r in rows:
            if not r.wa_id:
                continue
            if r.flow_type == "treatment":
                treatment_groups.setdefault(r.wa_id, []).append(r)
            elif r.flow_type == "lead_appointment":
                lead_appointment_groups.setdefault(r.wa_id, []).append(r)

        thank_you_keywords = [
            "thank you",
            "thankyou",
            "thank-you",
            "✅ thank you",
            "thank you!",
            "thank you 😊",
            "thank you 🙏",
        ]
        follow_up_keywords = [
            "follow-up",
            "follow up",
            "followup",
        ]

        def analyze_groups(groups: Dict[str, List[FlowLog]]) -> Dict[str, int]:
            totals = {
                "total": 0,
                "completed": 0,
                "followups": 0,
            }

            for wa_id, logs in groups.items():
                totals["total"] += 1
                descriptions = [
                    (log.description or "").lower()
                    for log in logs
                ]

                has_thank_you = any(
                    any(keyword in desc for keyword in thank_you_keywords)
                    for desc in descriptions
                )

                has_follow_up = any(
                    any(keyword in desc for keyword in follow_up_keywords)
                    for desc in descriptions
                )

                if has_thank_you:
                    totals["completed"] += 1
                elif has_follow_up:
                    totals["followups"] += 1
                # Remaining flows will be treated as pending (total - completed - followups)

            return totals

        treatment_totals = analyze_groups(treatment_groups)
        lead_totals = analyze_groups(lead_appointment_groups)

        def build_result(totals: Dict[str, int]) -> Dict[str, int]:
            pending = max(totals["total"] - totals["completed"] - totals["followups"], 0)
            return {
                "total": totals["total"],
                "completed": totals["completed"],
                "followups": totals["followups"],
                "pending": pending,
            }

        return {
            "success": True,
            "treatment": build_result(treatment_totals),
            "lead_appointment": build_result(lead_totals),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{log_id}")
def get_flow_log(
    log_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        log = db.query(FlowLog).filter(FlowLog.id == log_id).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")

        return {
            "success": True,
            "data": {
                "id": str(log.id),
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "flow_type": log.flow_type,
                "name": log.name,
                "step": log.step,
                "status_code": log.status_code,
                "wa_id": log.wa_id,
                "description": log.description,
                "response_json": log.response_json,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))