import io
from typing import List
import pandas as pd
from fastapi import APIRouter, Depends, File, UploadFile, Response
from sqlalchemy.orm import Session

from auth import get_current_user
from database.db import get_db
from schemas.campaign_schema import BulkTemplateRequest, CampaignOut, CampaignCreate, CampaignUpdate
from services import whatsapp_service, job_service, customer_service
from schemas.customer_schema import CustomerCreate
from typing import List, Optional
from pydantic import BaseModel
from fastapi import HTTPException, Body
from models.models import Cost, Template, CampaignRecipient
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

@router.get("/", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return campaign_service.get_all_campaigns(db)

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

@router.post("/{campaign_id}/upload-excel")
async def upload_campaign_excel(
    campaign_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Upload Excel with phone_number, name, params -> add recipients to campaign."""
    # Ensure campaign exists
    campaign = campaign_service.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Read Excel file into DataFrame
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    # Validate required column
    if "phone_number" not in df.columns:
        raise HTTPException(status_code=400, detail="Excel must have 'phone_number' column")

    # Iterate and create recipients
    recipients = []
    for _, row in df.iterrows():
        phone = str(row.get("phone_number"))
        if not phone:
            continue
        # Normalize pandas/numpy types in params to JSON-serializable primitives
        def to_jsonable(val):
            try:
                import pandas as pd
                import numpy as np
                if isinstance(val, (pd.Timestamp,)):
                    return val.isoformat()
                if isinstance(val, (pd.Series, pd.DataFrame)):
                    return val.to_dict()
                if isinstance(val, (np.integer,)):
                    return int(val)
                if isinstance(val, (np.floating,)):
                    return float(val)
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

        clean_params = {k: to_jsonable(row[k]) for k in df.columns if k not in ["phone_number", "name"] and pd.notnull(row[k])}

        rec = CampaignRecipient(
            campaign_id=campaign_id,
            phone_number=phone,
            name=row.get("name"),
            params=clean_params,
            status="PENDING"
        )
        recipients.append(rec)

    db.add_all(recipients)
    db.commit()

    return {"status": "uploaded", "count": len(recipients)}

@router.get("/{campaign_id}/recipients")
def get_campaign_recipients(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all Excel-uploaded recipients for a campaign."""
    campaign = campaign_service.get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    return campaign.recipients

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
    campaign = campaign_service.create_campaign(db, campaign_payload, user_id=current_user.id)

    job = job_service.create_job(db, campaign.id, current_user)
    campaign_service.run_campaign(campaign, job, db)
    return {
        "status": "queued",
        "campaign_id": str(campaign.id),
        "job_id": str(job.id),
        "customer_count": len(customers)
    }


class PersonalizedRecipientPayload(BaseModel):
    wa_id: str
    name: Optional[str] = None
    body_params: Optional[List[str]] = None
    header_text_params: Optional[List[str]] = None
    header_media_id: Optional[str] = None


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

    # Resolve customers
    customers = []
    for wa in (req.customer_wa_ids or []):
        cust = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa, name=""))
        customers.append(cust)
    if not customers and not req.personalized_recipients:
        raise HTTPException(status_code=400, detail="No valid customers provided")

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

    # Create campaign and run
    campaign_payload = CampaignCreate(
        name=req.campaign_name or f"Saved: {req.template_name}",
        description=req.campaign_description or "Run saved template campaign",
        customer_ids=[c.id for c in customers],
        content=content,
        type="template",
        campaign_cost_type=normalized_cost_type
    )
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
            db.refresh(campaign)
    job = job_service.create_job(db, campaign.id, current_user)
    campaign_service.run_campaign(campaign, job, db)
    return {
        "status": "queued",
        "campaign_id": str(campaign.id),
        "job_id": str(job.id),
        "customer_count": len(customers),
        "expected_body": expected_body,
        "expected_header_text": expected_header_text
    }


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