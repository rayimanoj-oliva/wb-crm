import re
import json
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

VALID_STATES = {
    "Andhra Pradesh", "Telangana", "Karnataka", "Tamil Nadu", "Kerala",
    "Maharashtra", "Delhi", "Uttar Pradesh", "Madhya Pradesh", "Rajasthan",
    "Bihar", "West Bengal", "Odisha", "Punjab", "Haryana", "Gujarat",
    "Jharkhand", "Chhattisgarh", "Assam", "Goa", "Uttarakhand",
    "Himachal Pradesh", "Tripura", "Meghalaya", "Manipur", "Nagaland",
    "Mizoram", "Arunachal Pradesh", "Sikkim", "Chandigarh", "Jammu and Kashmir",
    "Ladakh"
}

def normalize_phone(phone: str) -> str:
    """Normalize phone to a 10-digit number if possible."""
    phone = re.sub(r"\D", "", str(phone))  # remove spaces, +, -
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if len(phone) == 10:
        return phone
    return ""  # invalid

MANDATORY_FIELDS = {"Pincode", "Phone"}  # You can add FullName, City etc.

def validate_address_fields(data: dict):
    errors = []

    # Check mandatory fields are present and not empty
    for field in MANDATORY_FIELDS:
        if not data.get(field):
            errors.append(f"{field} is mandatory and missing")

    # Full Name: only letters and spaces
    if not re.fullmatch(r"[A-Za-z ]{2,50}", data.get("FullName", "")):
        errors.append("Invalid Full Name")

    # House No. + Street: should have digits + optional hyphen/slash
    if not re.search(r"\d", data.get("HouseStreet", "")):
        errors.append("Invalid House No. + Street (should contain a number)")

    # Locality: at least 3 chars, letters allowed
    if len(data.get("Locality", "")) < 3:
        errors.append("Invalid Locality")

    # City: should be text only
    if not re.fullmatch(r"[A-Za-z ]{2,50}", data.get("City", "")):
        errors.append("Invalid City")

    # State: must be in predefined list
    if data.get("State") not in VALID_STATES:
        errors.append("Invalid State")

    # Pincode: 6-digit starting 1-9
    if not re.fullmatch(r"[1-9][0-9]{5}", str(data.get("Pincode", ""))):
        errors.append("Invalid Pincode")

    # Phone Number (after normalization)
    phone = normalize_phone(data.get("Phone", ""))
    if not phone:
        errors.append("Invalid Phone Number")

    return errors


def extract_and_validate(input_text: str):
    # Step 1: Use LLM to parse fields with strict schema (camelcase keys)
    prompt = f"""
You are an Indian Address Extractor.  
Extract the following fields from text and return in *exact JSON key names*:
- FullName
- HouseStreet
- Locality
- City
- State
- Pincode
- Phone
- Landmark (optional)

Do NOT validate — just extract.
Text:
{input_text}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    data = json.loads(response.choices[0].message.content)

    # Step 2: Validate fields
    errors = validate_address_fields(data)

    # Step 3: True/False decision
    total_fields = 7
    valid_fields = total_fields - len(errors)
    return valid_fields / total_fields >= 0.5


def analyze_address(input_text: str):
    """Parse address text into fields and return (data, errors).

    Returns:
        tuple(dict, list[str]): Parsed fields dict and list of validation errors.
    """
    data = {}
    errors = ["Validation service unavailable"]
    try:
        prompt = f"""
You are an Indian Address Extractor.
Extract the following fields from text and return in exact JSON key names:
- FullName
- HouseStreet
- Locality
- City
- State
- Pincode
- Phone
- Landmark

Do NOT validate — just extract.
Text:
{input_text}
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        errors = validate_address_fields(data)
    except Exception:
        # Keep defaults; caller can decide fallback UX
        pass
    return data, errors


def format_errors_for_user(errors: list[str]) -> str:
    if not errors:
        return ""
    bullet_list = "\n".join([f"- {e}" for e in errors])
    return (
        "I couldn't verify your address. Please correct these fields and resend:\n"
        f"{bullet_list}\n\n"
        "Format reminder:\n"
        "Full Name:\nHouse No. + Street:\nArea / Locality:\nCity:\nState:\nPincode:\nPhone Number:\nLandmark (Optional):"
    )

if __name__ == '__main__':
    # Example input
    input_text = """
    Full Name:  Bogadi Bhargavi
    Area / Locality: 1-11
    House No. + Street:
    City:  Hyderabad
    State:  Telangana
    Pincode:  500000
    Landmark (Optional):
    Phone Number: +91 6304742913
    """

    result = extract_and_validate(input_text)
    print(result)  # → True or False