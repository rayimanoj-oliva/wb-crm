import re
from io import BytesIO
from typing import Dict, List, Tuple

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.models import Template
from utils.json_placeholder import extract_placeholders


def _get_template(db: Session, template_name: str) -> Template:
    template = db.query(Template).filter(Template.template_name == template_name).first()
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
    return template


def _placeholder_count(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\{\{[^\}]+\}\}", text))


def _extract_button_meta(components: List[Dict]) -> Dict:
    for comp in components:
        if comp.get("type", "").upper() == "BUTTONS":
            buttons = comp.get("buttons", [])
            for button in buttons:
                button_type = button.get("type", "").upper()
                if button_type == "URL":
                    url = button.get("url", "")
                    has_placeholders = "{{" in url and "}}" in url
                    return {
                        "has_buttons": True,
                        "button_type": "URL",
                        "button_requires_param": has_placeholders,
                        "button_index": str(button.get("index", "1")),
                    }
                elif button_type in {"QUICK_REPLY", "PHONE_NUMBER"}:
                    return {
                        "has_buttons": True,
                        "button_type": button_type,
                        "button_requires_param": False,
                        "button_index": str(button.get("index", "1")),
                    }
    return {
        "has_buttons": False,
        "button_type": None,
        "button_requires_param": False,
        "button_index": "1",
    }


def get_template_metadata(db: Session, template_name: str) -> Dict:
    template = _get_template(db, template_name)
    body = template.template_body or {}
    components = body.get("components", [])

    body_count = 0
    header_text_count = 0
    header_type = None

    for comp in components:
        comp_type = comp.get("type", "").upper()
        if comp_type == "BODY":
            body_text = comp.get("text", "")
            body_count = max(body_count, _placeholder_count(body_text))
        elif comp_type == "HEADER":
            format_type = (comp.get("format") or comp.get("format_type") or comp.get("header_type") or "").upper()
            if format_type in {"TEXT", "IMAGE", "DOCUMENT", "VIDEO"}:
                header_type = format_type
            if format_type == "TEXT":
                header_text = comp.get("text", "")
                header_text_count = max(header_text_count, _placeholder_count(header_text))

    button_meta = _extract_button_meta(components)

    placeholders = extract_placeholders(body)

    return {
        "template": template,
        "components": components,
        "body_placeholder_count": body_count,
        "header_text_placeholder_count": header_text_count,
        "header_type": header_type,
        "button_meta": button_meta,
        "raw_placeholders": placeholders,
    }


def build_excel_columns(meta: Dict) -> List[str]:
    columns = ["phone_number"]
    body_count = meta["body_placeholder_count"]
    header_count = meta["header_text_placeholder_count"]
    header_type = meta["header_type"]
    button_meta = meta["button_meta"]

    for idx in range(body_count):
        columns.append(f"body_var_{idx + 1}")

    if header_type == "TEXT":
        for idx in range(header_count):
            columns.append(f"header_var_{idx + 1}")
    elif header_type == "IMAGE":
        columns.append("header_media_id")

    if button_meta.get("button_type") == "URL":
        if button_meta.get("button_requires_param"):
            columns.append("button_param_1")
        else:
            columns.append("button_url")  # static suffix

    columns.append("name (optional)")
    return columns


def generate_excel_template(meta: Dict, template_name: str, language: str) -> BytesIO:
    columns = build_excel_columns(meta)
    df = pd.DataFrame(columns=columns)

    for idx, column in enumerate(columns):
        if column.startswith("body_var_"):
            df.at[0, column] = f"Body variable #{idx}"
        elif column.startswith("header_var_"):
            df.at[0, column] = f"Header variable #{idx}"
        elif column == "header_media_id":
            df.at[0, column] = "Upload media via /media/upload API and paste ID"
        elif column.startswith("button"):
            df.at[0, column] = "Button parameter / URL"
        elif column == "phone_number":
            df.at[0, column] = "E.g. 918309866859"
        else:
            df.at[0, column] = ""

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Recipients")
        workbook = writer.book
        summary_sheet = workbook.create_sheet("Instructions")
        summary_sheet["A1"] = f"Template: {template_name}"
        summary_sheet["A2"] = f"Language: {language}"
        summary_sheet["A3"] = "Fill the Recipients sheet and re-upload via portal."
        summary_sheet["A4"] = "Required Columns:"
        for idx, column in enumerate(columns, start=5):
            summary_sheet[f"A{idx}"] = f"- {column}"

    output.seek(0)
    return output


def build_excel_response(db: Session, template_name: str, language: str) -> Tuple[BytesIO, str]:
    meta = get_template_metadata(db, template_name)
    buffer = generate_excel_template(meta, template_name, language)
    safe_name = template_name.lower().replace(" ", "_")
    filename = f"{safe_name}_recipients.xlsx"
    return buffer, filename






