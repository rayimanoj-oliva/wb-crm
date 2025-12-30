from datetime import datetime, timedelta
from typing import Optional, Any, Dict, List, Tuple, Set
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text, func, case
import csv
import io
import json

from openpyxl import Workbook

from database.db import get_db
from models.models import FlowLog, Lead, Customer, Message

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


def _get_peer_numbers_for_customers(db: Session, wa_ids: List[str]) -> Dict[str, str]:
    """
    Get peer numbers (business WhatsApp numbers) for a list of customer wa_ids.
    Returns a dict mapping customer wa_id to their peer number.
    The peer number is the business number the customer messaged.
    """
    if not wa_ids:
        return {}
    
    # Get the first message for each customer to determine peer number
    # Peer number is the business number (to_wa_id when customer sent, from_wa_id when business sent)
    peer_subq = (
        db.query(
            Message.customer_id,
            func.min(Message.timestamp).label('first_timestamp')
        )
        .join(Customer, Message.customer_id == Customer.id)
        .filter(Customer.wa_id.in_(wa_ids))
        .group_by(Message.customer_id)
        .subquery()
    )
    
    peer_results = (
        db.query(
            Customer.wa_id,
            func.coalesce(
                case(
                    (Message.from_wa_id == Customer.wa_id, Message.to_wa_id),
                    else_=Message.from_wa_id
                ),
                ""
            ).label('peer_number')
        )
        .select_from(Message)
        .join(
            peer_subq,
            and_(
                Message.customer_id == peer_subq.c.customer_id,
                Message.timestamp == peer_subq.c.first_timestamp
            )
        )
        .join(Customer, Message.customer_id == Customer.id)
        .all()
    )
    
    return {wa_id: peer_number for wa_id, peer_number in peer_results if wa_id and peer_number}


def _extract_keywords_from_messages(db: Session, wa_ids: List[str]) -> Dict[str, str]:
    """
    Extract keywords from customer messages.
    Returns a dict mapping customer wa_id to comma-separated keywords found in their messages.
    """
    if not wa_ids:
        return {}
    
    # Define keywords to search for (case-insensitive)
    keywords = [
        "price",
        "appointment",
        "cost",
        "vacancy",
        "contact us",
        "clinic address",
        "clinic number",
        "treatment information",
        "treatment type",
    ]
    
    # Get all messages from customers
    messages = (
        db.query(
            Customer.wa_id,
            Message.body
        )
        .join(Message, Customer.id == Message.customer_id)
        .filter(Customer.wa_id.in_(wa_ids))
        .filter(Message.sender_type == "customer")  # Only customer messages
        .filter(Message.body.isnot(None))
        .all()
    )
    
    # Map wa_id to found keywords
    keyword_map: Dict[str, Set[str]] = {}
    for wa_id, body in messages:
        if not wa_id or not body:
            continue
        
        body_lower = body.lower()
        found_keywords = []
        
        for keyword in keywords:
            if keyword.lower() in body_lower:
                # Use the original keyword format for display
                found_keywords.append(keyword)
        
        if found_keywords:
            if wa_id not in keyword_map:
                keyword_map[wa_id] = set()
            keyword_map[wa_id].update(found_keywords)
    
    # Convert sets to comma-separated strings
    return {wa_id: ", ".join(sorted(keywords)) for wa_id, keywords in keyword_map.items()}


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
                # Include entire day when only a date is provided
                if date_to and len(date_to) == 10:
                    dt_to_upper = dt_to + timedelta(days=1)
                    filters.append(FlowLog.created_at < dt_to_upper)
                else:
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


@router.get("/export-pushed-leads")
def export_pushed_leads_excel(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Export leads pushed to Zoho (stored in leads table) as an Excel workbook.
    Results can be filtered by flow type and date range.
    """
    try:
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        dt_to_upper: Optional[datetime] = None
        if dt_to:
            # include entire day when only a date is provided
            if date_to and len(date_to) == 10:
                dt_to_upper = dt_to + timedelta(days=1)
            else:
                dt_to_upper = dt_to

        lead_query = db.query(Lead)
        if dt_from:
            lead_query = lead_query.filter(Lead.created_at >= dt_from)
        if dt_to_upper:
            lead_query = lead_query.filter(Lead.created_at < dt_to_upper)

        leads: List[Lead] = (
            lead_query.order_by(Lead.created_at.desc()).limit(20000).all()
        )

        if not leads:
            raise HTTPException(status_code=404, detail="No leads found for the selected filters.")

        log_filters = [
            FlowLog.step == "result",
            FlowLog.status_code == 200,
            FlowLog.response_json.isnot(None),
        ]
        if flow_type:
            log_filters.append(FlowLog.flow_type == flow_type)
        if dt_from:
            log_filters.append(FlowLog.created_at >= dt_from)
        if dt_to_upper:
            log_filters.append(FlowLog.created_at < dt_to_upper)

        flow_log_map: Dict[str, str] = {}
        wa_id_map: Dict[str, str] = {}

        log_rows = db.query(FlowLog).filter(and_(*log_filters)).all()
        for log in log_rows:
            if not log.response_json:
                continue
            lead_id: Optional[str] = None
            try:
                payload = json.loads(log.response_json)
                if isinstance(payload, dict):
                    if payload.get("success") and not payload.get("duplicate") and not payload.get("skipped"):
                        lead_id = payload.get("lead_id")
                        if not lead_id:
                            response_block = payload.get("response") or {}
                            data_list = response_block.get("data") or []
                            if data_list:
                                details = (data_list[0] or {}).get("details") or {}
                                lead_id = details.get("id")
            except Exception:
                continue

            if not lead_id:
                continue
            lead_id_str = str(lead_id)
            flow_log_map.setdefault(lead_id_str, log.flow_type or "")
            if log.wa_id:
                wa_id_map.setdefault(lead_id_str, log.wa_id)

        flow_type_labels = {
            "treatment": "Marketing",
            "lead_appointment": "Meta Ad Campaign",
        }

        def infer_flow_from_source(lead_source: Optional[str]) -> Optional[str]:
            if not lead_source:
                return None
            source_lower = lead_source.lower()
            if "business" in source_lower:
                return "treatment"
            if "facebook" in source_lower or "meta" in source_lower:
                return "lead_appointment"
            return None

        # Get peer numbers for all leads
        lead_wa_ids = [lead.wa_id for lead in leads if lead.wa_id]
        peer_number_map = _get_peer_numbers_for_customers(db, lead_wa_ids)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Pushed Leads"
        worksheet.append(["Name", "Lead ID", "Lead Source", "Sub Source", "Phone Number", "Peer Number", "Type of Flow", "Created At"])

        rows_written = 0
        for lead in leads:
            lead_id = lead.zoho_lead_id
            if not lead_id:
                continue

            flow_code = flow_log_map.get(lead_id) or infer_flow_from_source(lead.lead_source)
            if flow_type:
                if not flow_code:
                    continue
                if flow_code != flow_type:
                    continue

            flow_label = flow_type_labels.get(flow_code or "", flow_code or "Unknown")

            name_parts = [lead.first_name or "", lead.last_name or ""]
            name = " ".join(part.strip() for part in name_parts if part and part.strip()).strip() or "Unknown"

            phone = lead.phone or lead.mobile or wa_id_map.get(lead_id) or ""
            peer_number = peer_number_map.get(lead.wa_id, "")

            worksheet.append([
                name,
                lead_id,
                lead.lead_source or "",
                lead.sub_source or "",
                phone,
                peer_number,
                flow_label,
                lead.created_at.isoformat() if lead.created_at else "",
            ])
            rows_written += 1

        if rows_written == 0:
            raise HTTPException(status_code=404, detail="No leads matched the selected filters.")

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        suffix_parts = []
        if flow_type:
            suffix_parts.append(flow_type)
        if date_from:
            suffix_parts.append(f"from_{date_from}")
        if date_to:
            suffix_parts.append(f"to_{date_to}")
        suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=pushed_leads{suffix}.xlsx"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export-non-pushed-leads")
def export_non_pushed_leads_excel(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Export leads that started a flow but were NOT pushed to Zoho (no Lead entry).
    Results can be filtered by flow type and date range.
    """
    try:
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        dt_to_upper: Optional[datetime] = None
        if dt_to:
            if date_to and len(date_to) == 10:
                dt_to_upper = dt_to + timedelta(days=1)
            else:
                dt_to_upper = dt_to

        # Get all FlowLog entries that represent flow starts
        log_filters = [
            FlowLog.step.isnot(None),
            FlowLog.wa_id.isnot(None),
        ]
        if flow_type:
            log_filters.append(FlowLog.flow_type == flow_type)
        if dt_from:
            log_filters.append(FlowLog.created_at >= dt_from)
        if dt_to_upper:
            log_filters.append(FlowLog.created_at < dt_to_upper)

        # Get all unique wa_ids from FlowLog that have entries
        flow_log_wa_ids_result = (
            db.query(FlowLog.wa_id)
            .filter(and_(*log_filters))
            .distinct()
            .all()
        )
        flow_log_wa_ids_set = {row[0] for row in flow_log_wa_ids_result if row[0]}

        # Get all wa_ids that have Lead entries (pushed to Zoho)
        pushed_wa_ids_result = (
            db.query(Lead.wa_id)
            .distinct()
            .all()
        )
        pushed_wa_ids_set = {row[0] for row in pushed_wa_ids_result if row[0]}

        # Find wa_ids that are in FlowLog but NOT in Lead (non-pushed leads)
        non_pushed_wa_ids_set = flow_log_wa_ids_set - pushed_wa_ids_set
        non_pushed_wa_ids = list(non_pushed_wa_ids_set)

        if not non_pushed_wa_ids:
            raise HTTPException(status_code=404, detail="No non-pushed leads found for the selected filters.")

        # Get latest FlowLog entry for each non-pushed wa_id
        latest_log_subq = (
            db.query(
                FlowLog.wa_id,
                func.max(FlowLog.created_at).label('max_created_at')
            )
            .filter(FlowLog.wa_id.in_(non_pushed_wa_ids))
            .filter(and_(*log_filters))
            .group_by(FlowLog.wa_id)
            .subquery()
        )

        # Get full FlowLog entries with customer info
        results = (
            db.query(
                FlowLog,
                Customer.name,
                Customer.phone_1,
                Customer.email
            )
            .join(
                latest_log_subq,
                and_(
                    FlowLog.wa_id == latest_log_subq.c.wa_id,
                    FlowLog.created_at == latest_log_subq.c.max_created_at
                )
            )
            .outerjoin(Customer, FlowLog.wa_id == Customer.wa_id)
            .all()
        )

        # Get peer numbers for non-pushed leads
        non_pushed_wa_ids = [log.wa_id for log, _, _, _ in results if log.wa_id]
        peer_number_map = _get_peer_numbers_for_customers(db, non_pushed_wa_ids)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Non-Pushed Leads"
        worksheet.append([
            "Name", "Phone Number", "Email", "WA ID", "Peer Number", "Flow Type", "Last Step", 
            "Description", "Status Code", "Created At"
        ])

        rows_written = 0
        for log, customer_name, phone_1, email in results:
            name = customer_name or log.name or "Unknown"
            phone = phone_1 or log.wa_id or ""
            peer_number = peer_number_map.get(log.wa_id, "") if log.wa_id else ""
            
            worksheet.append([
                name,
                phone,
                email or "",
                log.wa_id or "",
                peer_number,
                log.flow_type or "",
                log.step or "",
                log.description or "",
                log.status_code or "",
                log.created_at.isoformat() if log.created_at else "",
            ])
            rows_written += 1

        if rows_written == 0:
            raise HTTPException(status_code=404, detail="No non-pushed leads matched the selected filters.")

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        suffix_parts = []
        if flow_type:
            suffix_parts.append(flow_type)
        if date_from:
            suffix_parts.append(f"from_{date_from}")
        if date_to:
            suffix_parts.append(f"to_{date_to}")
        suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=non_pushed_leads{suffix}.xlsx"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export-all-leads")
def export_all_leads_excel(
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Export all leads (both pushed and non-pushed) as a single Excel sheet.
    Results can be filtered by flow type and date range.
    """
    try:
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        dt_to_upper: Optional[datetime] = None
        if dt_to:
            if date_to and len(date_to) == 10:
                dt_to_upper = dt_to + timedelta(days=1)
            else:
                dt_to_upper = dt_to

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "All Leads"

        flow_type_labels = {
            "treatment": "Marketing",
            "lead_appointment": "Meta Ad Campaign",
        }

        def infer_flow_from_source(lead_source: Optional[str]) -> Optional[str]:
            if not lead_source:
                return None
            source_lower = lead_source.lower()
            if "business" in source_lower:
                return "treatment"
            if "facebook" in source_lower or "meta" in source_lower:
                return "lead_appointment"
            return None

        # Unified header with all columns
        worksheet.append([
            "Status", "Name", "Phone Number", "Email", "WA ID", "Lead ID", 
            "Lead Source", "Sub Source", "Peer Number", "Flow Type", 
            "Last Step", "Description", "Status Code", "Keywords", "Created At"
        ])

        lead_query = db.query(Lead)
        if dt_from:
            lead_query = lead_query.filter(Lead.created_at >= dt_from)
        if dt_to_upper:
            lead_query = lead_query.filter(Lead.created_at < dt_to_upper)

        leads: List[Lead] = (
            lead_query.order_by(Lead.created_at.desc()).limit(20000).all()
        )

        # Get peer numbers for all pushed leads
        all_wa_ids = []
        for lead in leads:
            if lead.wa_id:
                all_wa_ids.append(lead.wa_id)

        log_filters = [
            FlowLog.step == "result",
            FlowLog.status_code == 200,
            FlowLog.response_json.isnot(None),
        ]
        if flow_type:
            log_filters.append(FlowLog.flow_type == flow_type)
        if dt_from:
            log_filters.append(FlowLog.created_at >= dt_from)
        if dt_to_upper:
            log_filters.append(FlowLog.created_at < dt_to_upper)

        flow_log_map: Dict[str, str] = {}
        wa_id_map: Dict[str, str] = {}

        log_rows = db.query(FlowLog).filter(and_(*log_filters)).all()
        for log in log_rows:
            if not log.response_json:
                continue
            lead_id: Optional[str] = None
            try:
                payload = json.loads(log.response_json)
                if isinstance(payload, dict):
                    if payload.get("success") and not payload.get("duplicate") and not payload.get("skipped"):
                        lead_id = payload.get("lead_id")
                        if not lead_id:
                            response_block = payload.get("response") or {}
                            data_list = response_block.get("data") or []
                            if data_list:
                                details = (data_list[0] or {}).get("details") or {}
                                lead_id = details.get("id")
            except Exception:
                continue

            if not lead_id:
                continue
            lead_id_str = str(lead_id)
            flow_log_map.setdefault(lead_id_str, log.flow_type or "")
            if log.wa_id:
                wa_id_map.setdefault(lead_id_str, log.wa_id)

        # Get peer numbers for pushed leads
        pushed_peer_number_map = _get_peer_numbers_for_customers(db, all_wa_ids)

        # Get keywords from messages for pushed leads
        pushed_keywords_map = _extract_keywords_from_messages(db, all_wa_ids)

        # Get customer info for pushed leads
        pushed_wa_ids_list = [lead.wa_id for lead in leads if lead.wa_id]
        customer_map = {}
        if pushed_wa_ids_list:
            customers = db.query(Customer).filter(Customer.wa_id.in_(pushed_wa_ids_list)).all()
            customer_map = {c.wa_id: c for c in customers}

        pushed_rows_written = 0
        for lead in leads:
            lead_id = lead.zoho_lead_id
            if not lead_id:
                continue

            flow_code = flow_log_map.get(lead_id) or infer_flow_from_source(lead.lead_source)
            if flow_type:
                if not flow_code:
                    continue
                if flow_code != flow_type:
                    continue

            flow_label = flow_type_labels.get(flow_code or "", flow_code or "Unknown")

            name_parts = [lead.first_name or "", lead.last_name or ""]
            name = " ".join(part.strip() for part in name_parts if part and part.strip()).strip() or "Unknown"

            phone = lead.phone or lead.mobile or wa_id_map.get(lead_id) or ""
            peer_number = pushed_peer_number_map.get(lead.wa_id, "") if lead.wa_id else ""
            keywords = pushed_keywords_map.get(lead.wa_id, "") if lead.wa_id else ""
            
            # Get customer email if available
            customer = customer_map.get(lead.wa_id) if lead.wa_id else None
            email = customer.email if customer else ""

            worksheet.append([
                "Pushed",  # Status
                name,
                phone,
                email,
                lead.wa_id or "",
                lead_id,
                lead.lead_source or "",
                lead.sub_source or "",
                peer_number,
                flow_label,
                "",  # Last Step (not applicable for pushed leads)
                "",  # Description (not applicable for pushed leads)
                "",  # Status Code (not applicable for pushed leads)
                keywords,  # Keywords found in messages
                lead.created_at.isoformat() if lead.created_at else "",
            ])
            pushed_rows_written += 1

        log_filters_non_pushed = [
            FlowLog.step.isnot(None),
            FlowLog.wa_id.isnot(None),
        ]
        if flow_type:
            log_filters_non_pushed.append(FlowLog.flow_type == flow_type)
        if dt_from:
            log_filters_non_pushed.append(FlowLog.created_at >= dt_from)
        if dt_to_upper:
            log_filters_non_pushed.append(FlowLog.created_at < dt_to_upper)

        flow_log_wa_ids_result = (
            db.query(FlowLog.wa_id)
            .filter(and_(*log_filters_non_pushed))
            .distinct()
            .all()
        )
        flow_log_wa_ids_set = {row[0] for row in flow_log_wa_ids_result if row[0]}

        pushed_wa_ids_result = (
            db.query(Lead.wa_id)
            .distinct()
            .all()
        )
        pushed_wa_ids_set = {row[0] for row in pushed_wa_ids_result if row[0]}

        non_pushed_wa_ids_set = flow_log_wa_ids_set - pushed_wa_ids_set
        non_pushed_wa_ids = list(non_pushed_wa_ids_set)

        non_pushed_rows_written = 0
        if non_pushed_wa_ids:
            latest_log_subq = (
                db.query(
                    FlowLog.wa_id,
                    func.max(FlowLog.created_at).label('max_created_at')
                )
                .filter(FlowLog.wa_id.in_(non_pushed_wa_ids))
                .filter(and_(*log_filters_non_pushed))
                .group_by(FlowLog.wa_id)
                .subquery()
            )

            results = (
                db.query(
                    FlowLog,
                    Customer.name,
                    Customer.phone_1,
                    Customer.email
                )
                .join(
                    latest_log_subq,
                    and_(
                        FlowLog.wa_id == latest_log_subq.c.wa_id,
                        FlowLog.created_at == latest_log_subq.c.max_created_at
                    )
                )
                .outerjoin(Customer, FlowLog.wa_id == Customer.wa_id)
                .all()
            )

            # Get peer numbers for non-pushed leads
            non_pushed_wa_ids_list = [log.wa_id for log, _, _, _ in results if log.wa_id]
            non_pushed_peer_number_map = _get_peer_numbers_for_customers(db, non_pushed_wa_ids_list)
            
            # Get keywords from messages for non-pushed leads
            non_pushed_keywords_map = _extract_keywords_from_messages(db, non_pushed_wa_ids_list)

            for log, customer_name, phone_1, email in results:
                name = customer_name or log.name or "Unknown"
                phone = phone_1 or log.wa_id or ""
                peer_number = non_pushed_peer_number_map.get(log.wa_id, "") if log.wa_id else ""
                keywords = non_pushed_keywords_map.get(log.wa_id, "") if log.wa_id else ""
                
                flow_label = flow_type_labels.get(log.flow_type or "", log.flow_type or "Unknown")
                
                worksheet.append([
                    "Non-Pushed",  # Status
                    name,
                    phone,
                    email or "",
                    log.wa_id or "",
                    "",  # Lead ID (not applicable for non-pushed leads)
                    "",  # Lead Source (not applicable for non-pushed leads)
                    "",  # Sub Source (not applicable for non-pushed leads)
                    peer_number,
                    flow_label,
                    log.step or "",
                    log.description or "",
                    str(log.status_code) if log.status_code else "",
                    keywords,  # Keywords found in messages
                    log.created_at.isoformat() if log.created_at else "",
                ])
                non_pushed_rows_written += 1

        if pushed_rows_written == 0 and non_pushed_rows_written == 0:
            raise HTTPException(status_code=404, detail="No leads found for the selected filters.")

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        suffix_parts = []
        if flow_type:
            suffix_parts.append(flow_type)
        if date_from:
            suffix_parts.append(f"from_{date_from}")
        if date_to:
            suffix_parts.append(f"to_{date_to}")
        suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=all_leads{suffix}.xlsx"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export-chats-without-push")
def export_chats_without_push_excel(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Export customers who have messages (chats) but no FlowLog entries (never entered a flow).
    Results can be filtered by date range.
    """
    try:
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        dt_to_upper: Optional[datetime] = None
        if dt_to:
            if date_to and len(date_to) == 10:
                dt_to_upper = dt_to + timedelta(days=1)
            else:
                dt_to_upper = dt_to

        # Get all wa_ids that have messages (join Message with Customer)
        message_filters = []
        if dt_from:
            message_filters.append(Message.timestamp >= dt_from)
        if dt_to_upper:
            message_filters.append(Message.timestamp < dt_to_upper)

        customers_with_messages_query = (
            db.query(Customer.wa_id)
            .join(Message, Customer.id == Message.customer_id)
        )
        if message_filters:
            customers_with_messages_query = customers_with_messages_query.filter(and_(*message_filters))
        customers_with_messages_result = customers_with_messages_query.distinct().all()
        customers_with_messages_set = {row[0] for row in customers_with_messages_result if row[0]}

        # Get all wa_ids that have FlowLog entries (entered a flow)
        customers_with_flows_wa_ids = (
            db.query(FlowLog.wa_id)
            .distinct()
            .all()
        )
        customers_with_flows_set = {row[0] for row in customers_with_flows_wa_ids if row[0]}

        # Find customers with messages but NO FlowLog entries
        chats_without_flow_wa_ids = customers_with_messages_set - customers_with_flows_set

        if not chats_without_flow_wa_ids:
            raise HTTPException(status_code=404, detail="No chats without flow push found for the selected filters.")

        # Get customers
        customers_query = (
            db.query(Customer)
            .filter(Customer.wa_id.in_(list(chats_without_flow_wa_ids)))
        )

        if dt_from or dt_to_upper:
            # Also filter by customer creation date if date filters are provided
            customer_date_filters = []
            if dt_from:
                customer_date_filters.append(Customer.created_at >= dt_from)
            if dt_to_upper:
                customer_date_filters.append(Customer.created_at < dt_to_upper)
            if customer_date_filters:
                customers_query = customers_query.filter(and_(*customer_date_filters))

        customers = customers_query.order_by(Customer.created_at.desc()).limit(20000).all()

        if not customers:
            raise HTTPException(status_code=404, detail="No chats without flow push found for the selected filters.")

        # Get latest message for each customer (join via customer_id)
        customer_wa_ids = [c.wa_id for c in customers if c.wa_id]
        if not customer_wa_ids:
            message_map = {}
        else:
            latest_message_subq = (
                db.query(
                    Message.customer_id,
                    func.max(Message.timestamp).label('max_timestamp')
                )
                .join(Customer, Message.customer_id == Customer.id)
                .filter(Customer.wa_id.in_(customer_wa_ids))
                .group_by(Message.customer_id)
                .subquery()
            )

            latest_messages = (
                db.query(
                    Customer.wa_id,
                    Message.body,
                    Message.timestamp
                )
                .select_from(Message)
                .join(
                    latest_message_subq,
                    and_(
                        Message.customer_id == latest_message_subq.c.customer_id,
                        Message.timestamp == latest_message_subq.c.max_timestamp
                    )
                )
                .join(Customer, Message.customer_id == Customer.id)
                .all()
            )
            message_map = {wa_id: (body, timestamp) for wa_id, body, timestamp in latest_messages}

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Chats Without Push"
        worksheet.append([
            "Name", "Phone Number", "Email", "WA ID", "Last Message", "Last Message Time", "Created At"
        ])

        rows_written = 0
        for customer in customers:
            last_msg_body, last_msg_time = message_map.get(customer.wa_id, ("", None))
            
            name = customer.name or "Unknown"
            phone = customer.phone_1 or customer.wa_id or ""
            
            worksheet.append([
                name,
                phone,
                customer.email or "",
                customer.wa_id or "",
                (last_msg_body[:100] if last_msg_body else ""),  # Truncate long messages
                last_msg_time.isoformat() if last_msg_time else "",
                customer.created_at.isoformat() if customer.created_at else "",
            ])
            rows_written += 1

        if rows_written == 0:
            raise HTTPException(status_code=404, detail="No chats without flow push matched the selected filters.")

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        suffix_parts = []
        if date_from:
            suffix_parts.append(f"from_{date_from}")
        if date_to:
            suffix_parts.append(f"to_{date_to}")
        suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=chats_without_push{suffix}.xlsx"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lead-counts")
def get_lead_counts(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Return counts of leads pushed to Zoho, grouped by flow type.
    """
    try:
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        dt_to_upper: Optional[datetime] = None
        if dt_to:
            if date_to and len(date_to) == 10:
                dt_to_upper = dt_to + timedelta(days=1)
            else:
                dt_to_upper = dt_to

        lead_query = db.query(Lead)
        if dt_from:
            lead_query = lead_query.filter(Lead.created_at >= dt_from)
        if dt_to_upper:
            lead_query = lead_query.filter(Lead.created_at < dt_to_upper)

        leads: List[Lead] = lead_query.order_by(Lead.created_at.desc()).limit(20000).all()

        if not leads:
            return {
                "success": True,
                "overall": {"total_leads": 0, "unique_customers": 0},
                "treatment": {"total_leads": 0, "unique_customers": 0},
                "lead_appointment": {"total_leads": 0, "unique_customers": 0},
            }

        log_filters = [
            FlowLog.step == "result",
            FlowLog.status_code == 200,
            FlowLog.response_json.isnot(None),
        ]
        if dt_from:
            log_filters.append(FlowLog.created_at >= dt_from)
        if dt_to_upper:
            log_filters.append(FlowLog.created_at < dt_to_upper)

        flow_log_map: Dict[str, str] = {}
        log_rows = db.query(FlowLog).filter(and_(*log_filters)).all()
        for log in log_rows:
            if not log.response_json:
                continue
            try:
                payload = json.loads(log.response_json)
                if not isinstance(payload, dict):
                    continue
                if not payload.get("success"):
                    continue
                if payload.get("duplicate") or payload.get("skipped"):
                    continue
                lead_id = payload.get("lead_id")
                if not lead_id:
                    response_block = payload.get("response") or {}
                    data_list = response_block.get("data") or []
                    if data_list:
                        details = (data_list[0] or {}).get("details") or {}
                        lead_id = details.get("id")
                if not lead_id:
                    continue
                flow_log_map[str(lead_id)] = log.flow_type or ""
            except Exception:
                continue

        def infer_flow_from_source(lead_source: Optional[str]) -> Optional[str]:
            if not lead_source:
                return None
            lower = lead_source.lower()
            if "business" in lower:
                return "treatment"
            if "facebook" in lower or "meta" in lower:
                return "lead_appointment"
            return None

        counters = {
            "overall": {"total_leads": 0, "customers": set()},
            "treatment": {"total_leads": 0, "customers": set()},
            "lead_appointment": {"total_leads": 0, "customers": set()},
        }  # type: Dict[str, Dict[str, Any]]

        for lead in leads:
            lead_id = lead.zoho_lead_id
            if not lead_id:
                continue

            flow_code = flow_log_map.get(lead_id) or infer_flow_from_source(lead.lead_source)

            counters["overall"]["total_leads"] += 1
            if lead.wa_id:
                counters["overall"]["customers"].add(lead.wa_id)

            if flow_code in {"treatment", "lead_appointment"}:
                counters[flow_code]["total_leads"] += 1
                if lead.wa_id:
                    counters[flow_code]["customers"].add(lead.wa_id)

        def pack(flow_key: str) -> Dict[str, int]:
            entry = counters.get(flow_key) or {"total_leads": 0, "customers": set()}
            customers: Set[str] = entry.get("customers", set())  # type: ignore
            return {
                "total_leads": int(entry.get("total_leads", 0)),
                "unique_customers": len(customers),
            }

        return {
            "success": True,
            "overall": pack("overall"),
            "treatment": pack("treatment"),
            "lead_appointment": pack("lead_appointment"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lead-statistics")
def get_lead_statistics(
    db: Session = Depends(get_db),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Return detailed lead statistics including:
    - Total leads pushed to Zoho
    - Duplicates
    - Errors
    - Followups
    - Completed
    - Leads generated (followups + completed)
    """
    try:
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        dt_to_upper: Optional[datetime] = None
        if dt_to:
            if date_to and len(date_to) == 10:
                dt_to_upper = dt_to + timedelta(days=1)
            else:
                dt_to_upper = dt_to

        # Get all FlowLog entries in date range
        log_filters = []
        if dt_from:
            log_filters.append(FlowLog.created_at >= dt_from)
        if dt_to_upper:
            log_filters.append(FlowLog.created_at < dt_to_upper)

        query = db.query(FlowLog).filter(and_(*log_filters)) if log_filters else db.query(FlowLog)
        all_logs: List[FlowLog] = query.order_by(FlowLog.wa_id.asc(), FlowLog.created_at.asc()).all()

        # Group logs by wa_id
        groups: Dict[str, List[FlowLog]] = {}
        for log in all_logs:
            if not log.wa_id:
                continue
            groups.setdefault(log.wa_id, []).append(log)

        # Keywords for classification
        duplicate_keywords = ["duplicate", "duplicate avoided", "duplicate detected", "skipped", "already exists"]
        error_keywords = ["error", "failed", "exception", "timeout"]
        followup_keywords = ["follow-up", "follow up", "followup"]
        completion_keywords = ["thank you", "thankyou", "thank-you", "completed", "lead created"]

        # Counters
        total_leads_pushed = 0  # Actual leads in Lead table
        duplicates = 0
        errors = 0
        followups = 0
        completed = 0

        # Count actual leads pushed to Zoho (from Lead table)
        lead_query = db.query(Lead)
        if dt_from:
            lead_query = lead_query.filter(Lead.created_at >= dt_from)
        if dt_to_upper:
            lead_query = lead_query.filter(Lead.created_at < dt_to_upper)
        total_leads_pushed = lead_query.count()

        # Analyze each group
        for wa_id, logs in groups.items():
            sorted_logs = sorted(logs, key=lambda x: x.created_at or datetime.min, reverse=True)
            
            # Check for duplicates
            has_duplicate = False
            for log in sorted_logs:
                desc = (log.description or "").lower()
                response_json_str = log.response_json or ""
                
                # Check description for duplicate keywords
                if any(keyword in desc for keyword in duplicate_keywords):
                    has_duplicate = True
                    break
                
                # Check response_json for duplicate flag
                try:
                    if response_json_str:
                        payload = json.loads(response_json_str)
                        if isinstance(payload, dict) and (payload.get("duplicate") or payload.get("skipped")):
                            has_duplicate = True
                            break
                except Exception:
                    pass
            
            if has_duplicate:
                duplicates += 1
                continue

            # Check for errors
            has_error = False
            for log in sorted_logs:
                if log.status_code and log.status_code >= 400:
                    has_error = True
                    break
                desc = (log.description or "").lower()
                if any(keyword in desc for keyword in error_keywords):
                    has_error = True
                    break
            
            if has_error:
                errors += 1
                continue

            # Check for completion
            has_completion = False
            for log in sorted_logs:
                desc = (log.description or "").lower()
                step = (log.step or "").lower()
                status = log.status_code or 0
                
                # Check if step is "result" with 200 status
                if status >= 200 and status < 300 and step == "result":
                    # Verify it's not a duplicate by checking response_json
                    response_json_str = log.response_json or ""
                    try:
                        if response_json_str:
                            payload = json.loads(response_json_str)
                            if isinstance(payload, dict) and payload.get("success") and not payload.get("duplicate") and not payload.get("skipped"):
                                has_completion = True
                                break
                    except Exception:
                        pass
                
                # Check for completion keywords
                if any(keyword in desc for keyword in completion_keywords):
                    has_completion = True
                    break
            
            if has_completion:
                completed += 1
                continue

            # Check for followup
            has_followup = False
            for log in sorted_logs:
                step = (log.step or "").lower()
                desc = (log.description or "").lower()
                if any(keyword in step or keyword in desc for keyword in followup_keywords):
                    has_followup = True
                    break
            
            if has_followup:
                followups += 1
                continue

        # Leads generated = followups + completed
        leads_generated = followups + completed

        return {
            "success": True,
            "total_leads_pushed": total_leads_pushed,
            "duplicates": duplicates,
            "errors": errors,
            "followups": followups,
            "completed": completed,
            "leads_generated": leads_generated,  # followups + completed
        }
    except HTTPException:
        raise
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


class BatchLastStepRequest(BaseModel):
    """Request model for batch last-step lookup"""
    wa_ids: List[str]
    flow_type: Optional[str] = "lead_appointment"


@router.post("/last-step/batch")
def get_last_step_batch(
    request: BatchLastStepRequest,
    db: Session = Depends(get_db),
):
    """
    Get the last step reached for multiple customers in a single request.
    Much faster than calling /last-step/{wa_id} for each customer individually.

    Request body:
    {
        "wa_ids": ["919740498236", "919876543210", ...],
        "flow_type": "lead_appointment"  // or "treatment"
    }

    Returns:
    {
        "success": true,
        "total": 100,
        "results": {
            "919740498236": { "last_step": "city_selection", ... },
            "919876543210": { "last_step": null, "message": "No data found" },
            ...
        }
    }
    """
    try:
        wa_ids = request.wa_ids
        flow_type = request.flow_type

        if not wa_ids:
            return {"success": True, "total": 0, "results": {}}

        # Limit to prevent abuse
        if len(wa_ids) > 1000:
            raise HTTPException(status_code=400, detail="Maximum 1000 wa_ids allowed per request")

        # Normalize flow_type
        normalized_flow_type = flow_type
        if flow_type == "treatment_flow":
            normalized_flow_type = "treatment"
        elif flow_type == "lead_appointment_flow":
            normalized_flow_type = "lead_appointment"

        valid_steps = ["entry", "city_selection", "treatment", "concern_list", "last_step"]

        # Single query to get the latest step for ALL wa_ids at once
        # Using a subquery to get the max created_at per wa_id, then joining back
        from sqlalchemy import func
        from sqlalchemy.orm import aliased

        # Subquery: get max created_at per wa_id for valid steps
        subq = (
            db.query(
                FlowLog.wa_id,
                func.max(FlowLog.created_at).label("max_created_at")
            )
            .filter(
                and_(
                    FlowLog.wa_id.in_(wa_ids),
                    FlowLog.flow_type == normalized_flow_type,
                    FlowLog.step.in_(valid_steps)
                )
            )
            .group_by(FlowLog.wa_id)
            .subquery()
        )

        # Main query: join back to get full log data
        logs = (
            db.query(FlowLog)
            .join(
                subq,
                and_(
                    FlowLog.wa_id == subq.c.wa_id,
                    FlowLog.created_at == subq.c.max_created_at
                )
            )
            .filter(
                and_(
                    FlowLog.flow_type == normalized_flow_type,
                    FlowLog.step.in_(valid_steps)
                )
            )
            .all()
        )

        # Build results map
        results = {}
        found_wa_ids = set()

        for log in logs:
            found_wa_ids.add(log.wa_id)
            results[log.wa_id] = {
                "last_step": log.step,
                "step_name": log.step,
                "reached_at": log.created_at.isoformat() if log.created_at else None,
                "customer_name": log.name,
                "description": log.description,
            }

        # Add null entries for wa_ids not found
        for wa_id in wa_ids:
            if wa_id not in found_wa_ids:
                results[wa_id] = {
                    "last_step": None,
                    "message": "No step data found for this customer"
                }

        return {
            "success": True,
            "total": len(wa_ids),
            "found": len(found_wa_ids),
            "flow_type": normalized_flow_type,
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last-step/{wa_id}")
def get_last_step_reached(
    wa_id: str,
    db: Session = Depends(get_db),
    flow_type: Optional[str] = Query("lead_appointment", description="Flow type to check"),
):
    """
    Get the last step reached by a customer in a flow before follow-ups.
    Returns the most recent step from: entry, city_selection, treatment, concern_list, last_step
    
    Flow types:
    - "lead_appointment" or "lead_appointment_flow" -> searches for "lead_appointment"
    - "treatment" or "treatment_flow" -> searches for "treatment"
    """
    try:
        # Normalize flow_type (handle both "treatment_flow" and "treatment", etc.)
        normalized_flow_type = flow_type
        if flow_type == "treatment_flow":
            normalized_flow_type = "treatment"
        elif flow_type == "lead_appointment_flow":
            normalized_flow_type = "lead_appointment"
        
        # Valid steps for both flows
        valid_steps = ["entry", "city_selection", "treatment", "concern_list", "last_step"]
        
        # Query for the most recent valid step for this customer
        # Filter by step and description pattern (more flexible - matches any description containing "Last step reached")
        log = (
            db.query(FlowLog)
            .filter(
                and_(
                    FlowLog.wa_id == wa_id,
                    FlowLog.flow_type == normalized_flow_type,
                    FlowLog.step.in_(valid_steps),
                    or_(
                        FlowLog.description.like("%Last step reached:%"),
                        FlowLog.description == None  # Also include logs without description if step matches
                    )
                )
            )
            .order_by(FlowLog.created_at.desc())
            .first()
        )
        
        # If no log found with description filter, try without description filter (in case format changed)
        if not log:
            log = (
                db.query(FlowLog)
                .filter(
                    and_(
                        FlowLog.wa_id == wa_id,
                        FlowLog.flow_type == normalized_flow_type,
                        FlowLog.step.in_(valid_steps)
                    )
                )
                .order_by(FlowLog.created_at.desc())
                .first()
            )
        
        if not log:
            # Debug: Check if there are any logs at all for this customer
            any_logs = db.query(FlowLog).filter(
                and_(
                    FlowLog.wa_id == wa_id,
                    FlowLog.flow_type == normalized_flow_type
                )
            ).count()
            
            return {
                "success": True,
                "wa_id": wa_id,
                "flow_type": flow_type,
                "normalized_flow_type": normalized_flow_type,
                "last_step": None,
                "message": "No step data found for this customer",
                "debug": {
                    "total_logs_for_customer": any_logs,
                    "valid_steps_checked": valid_steps
                }
            }
        
        return {
            "success": True,
            "wa_id": wa_id,
            "flow_type": flow_type,
            "normalized_flow_type": normalized_flow_type,
            "last_step": log.step,
            "step_name": log.step,
            "reached_at": log.created_at.isoformat() if log.created_at else None,
            "customer_name": log.name,
            "description": log.description,
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