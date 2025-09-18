from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from utils.address_validator import extract_and_validate

router = APIRouter(tags=["Address Validation"])


class AddressRequest(BaseModel):
    text: str


class AddressResponse(BaseModel):
    data: Dict[str, Any]
    errors: list[str]
    suggestions: Dict[str, str]  # <-- New field


@router.post("/validate", response_model=AddressResponse)
async def validate_address(payload: AddressRequest):
    """
    Validate raw Indian address text.
    - Uses OpenAI to extract structured fields
    - Regex rules for format validation
    - OpenAI for Pincode/State/City consistency
    """
    try:
        data, errors, suggestions = extract_and_validate(payload.text)
        return {"data": data, "errors": errors, "suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")
