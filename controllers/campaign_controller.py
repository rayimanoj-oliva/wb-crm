import io
from typing import List
import pandas as pd
from fastapi import APIRouter, Depends, File, UploadFile, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from database.db import get_db
from schemas.campaign_schema import (
    BulkTemplateRequest,
    CampaignOut,
    CampaignCreate,
    CampaignUpdate,
    TemplateCampaignCreateRequest,
    TemplateExcelColumnsResponse,
    TemplateCampaignRunRequest,
)
from services import whatsapp_service, job_service, customer_service
from schemas.customer_schema import CustomerCreate
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import HTTPException, Body, Query
from models.models import Cost, Template, CampaignRecipient, Campaign, CampaignLog
from sqlalchemy import func
from services.campaign_service import (
    create_campaign,
    get_all_campaigns,
    get_campaign_reports,
    export_campaign_reports_excel,
    get_single_campaign_report,
    get_campaigns_running_in_date_range,
    export_single_campaign_report_excel,
)
import services.campaign_service as campaign_service
from uuid import UUID
from services.template_excel_service import (
    build_excel_response,
    get_template_metadata,
    build_excel_columns,
)
router = APIRouter(tags=["Campaign"])

# ------------------------------
# Campaign Reports Endpoints (placed before dynamic /{campaign_id})
# ------------------------------




@router.post("/send-template")
def send_bulk_template(req: BulkTemplateRequest):
    for client in req.clients:
        whatsapp_service.enqueue_template_message(
            to=client.wa_id,
            template_name=req.template_name,
            parameters=client.parameters
        )
    return {"status": "queued", "count": len(req.clients)}

@router.get("/")
def list_campaigns(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search by campaign name or description"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List campaigns with pagination and optional search."""
    return campaign_service.get_all_campaigns(db, skip=skip, limit=limit, search=search)

@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.get_campaign(db, campaign_id)

@router.post("/", response_model=CampaignOut)
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.create_campaign(db, campaign, user_id=current_user.id)

@router.put("/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: UUID, updates: CampaignUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.update_campaign(db, campaign_id, updates, user_id=current_user.id)

@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: UUID, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.delete_campaign(db, campaign_id)

@router.post("/run/{campaign_id}")
def run_campaign(campaign_id:UUID,db :Session = Depends(get_db),current_user: dict = Depends(get_current_user)):
    job = job_service.create_job(db, campaign_id,current_user)
    campaign = campaign_service.get_campaign(db,campaign_id)
    return campaign_service.run_campaign(campaign,job,db)


@router.post("/template", response_model=CampaignOut)
def create_template_campaign(
    payload: TemplateCampaignCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    template_meta = get_template_metadata(db, payload.template_name)
    template_body = template_meta["template"].template_body or {}
    content = {
        "name": payload.template_name,
        "language": payload.template_language,
        "components": template_body.get("components", []),
        "image_id": payload.image_id,
        "button_sub_type": payload.button_sub_type,
        "button_index": payload.button_index,
    }
    campaign_payload = CampaignCreate(
        name=payload.campaign_name,
        description=payload.description,
        customer_ids=[],
        content=content,
        type="template",
        campaign_cost_type=payload.campaign_cost_type,
    )
    campaign = campaign_service.create_campaign(db, campaign_payload, user_id=current_user.id)
    return campaign


@router.get("/template/{template_name}/excel-columns", response_model=TemplateExcelColumnsResponse)
def get_template_excel_columns(template_name: str, db: Session = Depends(get_db)):
    meta = get_template_metadata(db, template_name)
    columns = build_excel_columns(meta)
    button_meta = meta["button_meta"]
    return TemplateExcelColumnsResponse(
        template_name=template_name,
        columns=columns,
        body_placeholder_count=meta["body_placeholder_count"],
        header_placeholder_count=meta["header_text_placeholder_count"],
        header_type=meta["header_type"],
        has_buttons=button_meta.get("has_buttons", False),
        button_type=button_meta.get("button_type"),
    )


@router.get("/template/{template_name}/excel")
def download_template_excel(
    template_name: str,
    language: str = "en_US",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    buffer, filename = build_excel_response(db, template_name, language)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

def _normalize_phone(value: str) -> str:
    digits = "".join(filter(str.isdigit, value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


@router.post("/{campaign_id}/upload-excel")
async def upload_campaign_excel(
    campaign_id: UUID,
    file: UploadFile = File(...),
    clear_existing: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Upload Excel with phone_number, name, params -> add recipients to campaign.

    Args:
        campaign_id: Campaign UUID
        file: Excel file with phone_number column (required), name and other params (optional)
        clear_existing: If True, removes all existing recipients before adding new ones
    """
    import numpy as np

    # Ensure campaign exists
    campaign = campaign_service.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        contents = await file.read()
        # Limit file size to 10MB
        if len(contents) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        df = pd.read_excel(io.BytesIO(contents))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    # Limit row count
    if len(df) > 10000:
        raise HTTPException(status_code=400, detail="Excel file exceeds 10,000 rows limit")

    # Validate required column
    if "phone_number" not in df.columns:
        raise HTTPException(status_code=400, detail="Excel must have 'phone_number' column")

    # Clear existing recipients if requested
    if clear_existing:
        db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id).delete()

    # Get existing phone numbers to check for duplicates
    existing_phones = set()
    if not clear_existing:
        existing_recipients = db.query(CampaignRecipient.phone_number).filter(
            CampaignRecipient.campaign_id == campaign_id
        ).all()
        existing_phones = {r.phone_number for r in existing_recipients}

    # Phone number validation helper
    def is_valid_phone(phone: str) -> bool:
        if not phone:
            return False
        cleaned = phone.replace("+", "").replace(" ", "").replace("-", "")
        return len(cleaned) >= 10 and cleaned.isdigit()

    # Normalize pandas/numpy types in params to JSON-serializable primitives
    def to_jsonable(val):
        try:
            # Handle pandas NaT and NaN
            if pd.isna(val) or (isinstance(val, float) and np.isnan(val)):
                return None
            if isinstance(val, (pd.Timestamp,)):
                return val.isoformat()
            if isinstance(val, (pd.Series, pd.DataFrame)):
                return val.to_dict()
            if isinstance(val, (np.integer,)):
                return int(val)
            if isinstance(val, (np.floating,)):
                return float(val) if not np.isnan(val) else None
            if isinstance(val, (np.bool_,)):
                return bool(val)
        except Exception:
            pass
        # Datetime from Python
        try:
            from datetime import datetime
            if isinstance(val, datetime):
                return val.isoformat()
        except Exception:
            pass
        return val

    # Track statistics
    recipients = []
    skipped_invalid = 0
    skipped_duplicate = 0
    processed_phones_in_batch = set()

    for _, row in df.iterrows():
        # FIX: Properly handle None/NaN phone numbers
        raw_phone = row.get("phone_number")
        if pd.isna(raw_phone) or raw_phone is None:
            skipped_invalid += 1
            continue

        phone = str(raw_phone).strip()

        # Skip empty or invalid phone numbers
        if not phone or phone.lower() in ("none", "nan", "null", ""):
            skipped_invalid += 1
            continue

        # Validate phone number format
        if not is_valid_phone(phone):
            skipped_invalid += 1
            continue

        # Check for duplicates (existing + within this batch)
        if phone in existing_phones or phone in processed_phones_in_batch:
            skipped_duplicate += 1
            continue

        processed_phones_in_batch.add(phone)

        # Handle name field - also check for NaN
        raw_name = row.get("name")
        name = str(raw_name).strip() if pd.notna(raw_name) and raw_name is not None else None
        if name and name.lower() in ("none", "nan", "null"):
            name = None

        clean_params = {
            k: to_jsonable(row[k])
            for k in df.columns
            if k not in ["phone_number", "name"] and pd.notnull(row[k])
        }

        rec = CampaignRecipient(
            campaign_id=campaign_id,
            phone_number=phone,
            name=name,
            params=clean_params,
            status="PENDING"
        )
        recipients.append(rec)

    if recipients:
        db.add_all(recipients)
        db.commit()

    return {
        "status": "uploaded",
        "count": len(recipients),
        "skipped_invalid_phone": skipped_invalid,
        "skipped_duplicate": skipped_duplicate,
        "cleared_existing": clear_existing
    }


@router.post("/{campaign_id}/run-template")
def run_template_campaign(
    campaign_id: UUID,
    payload: TemplateCampaignRunRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign.type != "template":
        raise HTTPException(status_code=400, detail="Campaign is not a template campaign")
    job = job_service.create_job(db, campaign_id, current_user)
    campaign_service.run_campaign(
        campaign,
        job,
        db,
        batch_size=payload.batch_size,
        batch_delay=payload.batch_delay_seconds,
    )
    return {"status": "queued", "campaign_id": str(campaign.id), "job_id": str(job.id)}

@router.get("/{campaign_id}/recipients")
def get_campaign_recipients(
    campaign_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    status: Optional[str] = Query(None, description="Filter by status (PENDING, SENT, FAILED, QUEUED)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get Excel-uploaded recipients for a campaign with pagination."""
    campaign = campaign_service.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Build query with filters
    query = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id)

    if status:
        query = query.filter(CampaignRecipient.status == status.upper())

    total = query.count()
    recipients = query.offset(skip).limit(limit).all()

    return {"items": recipients, "total": total, "skip": skip, "limit": limit}

class QuickTemplateRunRequest(BaseModel):
    template_name: str
    language: str = "en_US"
    customer_wa_ids: List[str]
    body_params: Optional[List[str]] = None
    header_text_params: Optional[List[str]] = None
    header_media_id: Optional[str] = None
    # Optional helpers to match Meta expected body variable count
    body_expected: Optional[int] = None
    enforce_count: bool = False
    campaign_name: Optional[str] = None
    campaign_description: Optional[str] = None
    campaign_cost_type: Optional[str] = None


@router.post("/template/run-quick")
def run_template_campaign_quick(
    req: QuickTemplateRunRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create and run a template campaign in one call using wa_ids.

    - Resolves/creates customers by wa_id and associates them to a new campaign
    - Builds WhatsApp template components (header text/image + body params)
    - Creates a Job and enqueues tasks via the existing worker pipeline
    """
    customers = []
    for wa in req.customer_wa_ids:
        cust = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa, name=""))
        customers.append(cust)
    if not customers:
        raise HTTPException(status_code=400, detail="No valid customers provided")

    components: List[dict] = []
    if req.header_media_id:
        components.append({
            "type": "header",
            "parameters": [
                {"type": "image", "image": {"id": req.header_media_id}}
            ]
        })
    elif req.header_text_params:
        components.append({
            "type": "header",
            "parameters": [{"type": "text", "text": v} for v in req.header_text_params]
        })

    if req.body_params:
        body_vals = list(req.body_params)
        if req.enforce_count and isinstance(req.body_expected, int) and req.body_expected >= 0:
            expected = req.body_expected
            if len(body_vals) < expected:
                body_vals += ["-"] * (expected - len(body_vals))
            elif len(body_vals) > expected:
                body_vals = body_vals[:expected]
        else:
            body_vals = req.body_params
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": v} for v in body_vals]
        })

    content = {
        "name": req.template_name,
        "language": req.language,
        "components": components
    }

    # Validate/normalize campaign_cost_type against costs table to avoid FK errors
    normalized_cost_type = req.campaign_cost_type
    if normalized_cost_type:
        exists = db.query(Cost).filter(Cost.type == normalized_cost_type).first()
        if not exists:
            normalized_cost_type = None

    campaign_payload = CampaignCreate(
        name=req.campaign_name or f"Quick: {req.template_name}",
        description=req.campaign_description or "Quick template campaign",
        customer_ids=[c.id for c in customers],
        content=content,
        type="template",
        campaign_cost_type=normalized_cost_type
    )

    try:
        campaign = campaign_service.create_campaign(db, campaign_payload, user_id=current_user.id)
        job = job_service.create_job(db, campaign.id, current_user)
        campaign_service.run_campaign(campaign, job, db)

        return {
            "status": "queued",
            "campaign_id": str(campaign.id),
            "job_id": str(job.id),
            "customer_count": len(customers)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create or run campaign: {str(e)}"
        )


class PersonalizedRecipientPayload(BaseModel):
    wa_id: str
    name: Optional[str] = None
    body_params: Optional[List[str]] = None
    header_text_params: Optional[List[str]] = None
    header_media_id: Optional[str] = None
    # Optional template button support (e.g. URL button with dynamic parameter)
    # These map directly to WhatsApp "button" component fields
    button_params: Optional[List[str]] = None
    button_index: Optional[str] = "1"
    button_sub_type: Optional[str] = "url"


class RunSavedTemplateRequest(BaseModel):
    template_name: str
    language: str = "en_US"
    customer_wa_ids: Optional[List[str]] = None
    body_params: Optional[List[str]] = None
    header_text_params: Optional[List[str]] = None
    header_media_id: Optional[str] = None
    enforce_count: bool = True
    body_expected: Optional[int] = None
    header_text_expected: Optional[int] = None
    campaign_name: Optional[str] = None
    campaign_description: Optional[str] = None
    campaign_cost_type: Optional[str] = None
    personalized_recipients: Optional[List[PersonalizedRecipientPayload]] = None


@router.post("/template/run-saved")
def run_saved_template_campaign(
    req: RunSavedTemplateRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Load saved template definition if present
    tpl = db.query(Template).filter(Template.template_name == req.template_name).first()

    # Infer expected counts
    expected_body = req.body_expected
    expected_header_text = req.header_text_expected
    if tpl and isinstance(tpl.template_vars, dict):
        tv = tpl.template_vars
        try:
            if expected_body is None:
                body_val = tv.get("body")
                if isinstance(body_val, int):
                    expected_body = body_val
                elif isinstance(body_val, list):
                    expected_body = len(body_val)
            if expected_header_text is None:
                header_val = tv.get("header_text") or tv.get("header")
                if isinstance(header_val, int):
                    expected_header_text = header_val
                elif isinstance(header_val, list):
                    expected_header_text = len(header_val)
        except Exception:
            pass

    # Resolve customers from both direct wa_ids and personalized recipients
    customers_by_wa: Dict[str, Any] = {}

    def add_customer(wa_id: Optional[str], name: str = ""):
        if not wa_id:
            return None
        normalized = str(wa_id).strip()
        if not normalized:
            return None
        if normalized in customers_by_wa:
            return customers_by_wa[normalized]
        cust = customer_service.get_or_create_customer(
            db,
            CustomerCreate(wa_id=normalized, name=name or ""),
        )
        customers_by_wa[normalized] = cust
        return cust

    # Only add customers from customer_wa_ids (not from personalized_recipients)
    # When personalized_recipients are used, we process them separately as recipients
    # This prevents duplicate sends to the same phone numbers
    for wa in (req.customer_wa_ids or []):
        add_customer(wa)

    # NOTE: We do NOT add personalized_recipients as customers here
    # They will be processed as CampaignRecipient entries instead
    # This prevents duplicate processing in run_campaign

    customers = list(customers_by_wa.values())

    # Validate: must have either customers OR personalized_recipients
    if not customers and not req.personalized_recipients:
        raise HTTPException(status_code=400, detail="No valid customers or recipients provided")

    # Build components with padding/trimming
    components: List[dict] = []

    # Header handling
    if req.header_media_id:
        components.append({
            "type": "header",
            "parameters": [
                {"type": "image", "image": {"id": req.header_media_id}}
            ]
        })
    elif req.header_text_params:
        header_vals = list(req.header_text_params)
        if req.enforce_count and isinstance(expected_header_text, int) and expected_header_text >= 0:
            if len(header_vals) < expected_header_text:
                header_vals += ["-"] * (expected_header_text - len(header_vals))
            elif len(header_vals) > expected_header_text:
                header_vals = header_vals[:expected_header_text]
        components.append({
            "type": "header",
            "parameters": [{"type": "text", "text": v} for v in header_vals]
        })

    # Body handling
    if req.body_params:
        body_vals = list(req.body_params)
        if req.enforce_count and isinstance(expected_body, int) and expected_body >= 0:
            if len(body_vals) < expected_body:
                body_vals += [""] * (expected_body - len(body_vals))
            elif len(body_vals) > expected_body:
                body_vals = body_vals[:expected_body]
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": v} for v in body_vals]
        })

    content = {
        "name": req.template_name,
        "language": req.language,
        "components": components
    }

    # Normalize cost type
    normalized_cost_type = req.campaign_cost_type
    if normalized_cost_type:
        exists = db.query(Cost).filter(Cost.type == normalized_cost_type).first()
        if not exists:
            normalized_cost_type = None

    # Create campaign and run with transaction handling
    campaign_payload = CampaignCreate(
        name=req.campaign_name or f"Saved: {req.template_name}",
        description=req.campaign_description or "Run saved template campaign",
        customer_ids=[c.id for c in customers],
        content=content,
        type="template",
        campaign_cost_type=normalized_cost_type
    )

    try:
        campaign = campaign_service.create_campaign(db, campaign_payload, user_id=current_user.id)

        # Attach personalized recipients if provided
        personalized_entries = []
        if req.personalized_recipients:
            for rec in req.personalized_recipients:
                params = {}
                if rec.body_params is not None:
                    params["body_params"] = rec.body_params
                if rec.header_text_params is not None:
                    params["header_text_params"] = rec.header_text_params
                if rec.header_media_id is not None:
                    params["header_media_id"] = rec.header_media_id
                # Optional button params for templates that use dynamic button variables
                if rec.button_params is not None:
                    params["button_params"] = rec.button_params
                if rec.button_index is not None:
                    params["button_index"] = rec.button_index
                if rec.button_sub_type is not None:
                    params["button_sub_type"] = rec.button_sub_type
                personalized_entries.append(
                    CampaignRecipient(
                        campaign_id=campaign.id,
                        phone_number=rec.wa_id,
                        name=rec.name,
                        params=params if params else {},  # Always store as dict, never None
                    )
                )
            if personalized_entries:
                db.add_all(personalized_entries)
                db.commit()
                # Explicitly refresh and load recipients relationship
                db.refresh(campaign)
                # Force load recipients relationship
                _ = campaign.recipients  # Access to trigger lazy load

        job = job_service.create_job(db, campaign.id, current_user)

        # Ensure recipients are loaded before running campaign
        if req.personalized_recipients:
            # Re-query to ensure recipients are loaded
            from sqlalchemy.orm import joinedload
            campaign_with_recipients = db.query(Campaign).options(joinedload(Campaign.recipients)).filter_by(id=campaign.id).first()
            if campaign_with_recipients:
                campaign = campaign_with_recipients

        campaign_service.run_campaign(campaign, job, db)

        return {
            "status": "queued",
            "campaign_id": str(campaign.id),
            "job_id": str(job.id),
            "customer_count": len(customers),
            "recipient_count": len(personalized_entries) if req.personalized_recipients else 0,
            "expected_body": expected_body,
            "expected_header_text": expected_header_text
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create or run campaign: {str(e)}"
        )


# ------------------------------
# Campaign Reports Endpoints
# ------------------------------


@router.get("/reports/running")
def campaigns_running(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 25,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Parse dates in YYYY-MM-DD or DD-MM-YYYY
    def parse_d(d: Optional[str]):
        if not d:
            return None
        from datetime import datetime
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(d, fmt).date()
            except Exception:
                continue
        return None
    fd = parse_d(from_date)
    td = parse_d(to_date)

    rows = get_campaigns_running_in_date_range(
        db,
        from_date=fd,
        to_date=td,
        type_filter=type,
        search=search,
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return rows
@router.get("/{campaign_id}/report")
def campaign_report_detail(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return get_single_campaign_report(db, campaign_id)

@router.get("/{campaign_id}/report/export")
def campaign_report_export(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    content = export_single_campaign_report_excel(db, campaign_id)
    filename = f"campaign_{campaign_id}_report.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return Response(content=content, media_type=headers["Content-Type"], headers=headers)


# ------------------------------
# Campaign Logs Endpoints (Message Delivery Tracking)
# ------------------------------

@router.get("/{campaign_id}/logs")
def get_campaign_logs(
    campaign_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status (success, failure, pending, queued)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get delivery logs for a campaign with pagination.

    Returns:
        Paginated log entries with delivery status, phone numbers, errors, etc.
    """
    # Verify campaign exists
    campaign = campaign_service.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Build query
    query = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign_id)

    if status:
        query = query.filter(CampaignLog.status == status)

    # Get total count before pagination
    total = query.count()

    # Order by created_at desc and paginate
    logs = query.order_by(CampaignLog.created_at.desc()).offset(skip).limit(limit).all()

    items = [
        {
            "id": str(log.id),
            "phone_number": log.phone_number,
            "status": log.status,
            "error_code": log.error_code,
            "error_message": log.error_message,
            "whatsapp_message_id": log.whatsapp_message_id,
            "http_status_code": log.http_status_code,
            "processing_time_ms": log.processing_time_ms,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "processed_at": log.processed_at.isoformat() if log.processed_at else None,
        }
        for log in logs
    ]

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{campaign_id}/stats")
def get_campaign_stats(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get delivery statistics for a campaign.

    Returns:
        {
            "total": 100,
            "success": 95,
            "failure": 5,
            "pending": 0,
            "success_rate": 95.0
        }
    """
    # Verify campaign exists
    campaign = campaign_service.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get counts by status
    stats = db.query(
        CampaignLog.status,
        func.count(CampaignLog.id).label("count")
    ).filter(
        CampaignLog.campaign_id == campaign_id
    ).group_by(CampaignLog.status).all()

    # Build response
    result = {
        "total": 0,
        "success": 0,
        "failure": 0,
        "pending": 0,
        "queued": 0,
    }

    for status, count in stats:
        result["total"] += count
        if status in result:
            result[status] = count

    # Calculate success rate
    result["success_rate"] = round((result["success"] / result["total"] * 100), 2) if result["total"] > 0 else 0.0

    return result
