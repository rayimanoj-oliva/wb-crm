import re
import json
import os
from openai import OpenAI

# Init OpenAI client lazily and optionally
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None

VALID_STATES = {
    "Andhra Pradesh", "Telangana", "Karnataka", "Tamil Nadu", "Kerala",
    "Maharashtra", "Delhi", "Uttar Pradesh", "Madhya Pradesh", "Rajasthan",
    "Bihar", "West Bengal", "Odisha", "Punjab", "Haryana", "Gujarat",
    "Jharkhand", "Chhattisgarh", "Assam", "Goa", "Uttarakhand",
    "Himachal Pradesh", "Tripura", "Meghalaya", "Manipur", "Nagaland",
    "Mizoram", "Arunachal Pradesh", "Sikkim", "Chandigarh", "Jammu and Kashmir",
    "Ladakh"
}

MANDATORY_FIELDS = {"Pincode", "City", "State", "Locality", "HouseStreet"}


def normalize_phone(phone: str) -> str:
    phone = re.sub(r"\D", "", str(phone))
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    return phone if len(phone) == 10 else ""


def validate_address_fields(data: dict):
    errors = []
    suggestions = {}

    # Mandatory fields
    for field in MANDATORY_FIELDS:
        if not data.get(field):
            errors.append(f"{field} is mandatory and missing")

    # Full Name
    if not re.fullmatch(r"[A-Za-z ]{2,50}", data.get("FullName", "")):
        errors.append("Invalid Full Name")

    # HouseStreet
    if not re.search(r"\d", data.get("HouseStreet", "")):
        errors.append("Invalid HouseStreet (should contain a number)")

    # Locality
    if len(data.get("Locality", "")) < 3:
        errors.append("Invalid Locality")

    # City
    if not re.fullmatch(r"[A-Za-z ]{2,50}", data.get("City", "")):
        errors.append("Invalid City")

    # State
    state = data.get("State", "")
    if state not in VALID_STATES:
        errors.append("Invalid State")

    # Pincode
    pincode = str(data.get("Pincode", "")).strip()
    if not re.fullmatch(r"[1-9][0-9]{5}", pincode):
        errors.append("Invalid Pincode")

    # Phone
    phone = normalize_phone(data.get("Phone", ""))
    if not phone:
        errors.append("Invalid Phone Number")

    # ✅ OpenAI-based validation for State + City
    if client and re.fullmatch(r"[1-9][0-9]{5}", pincode) and state and data.get("City"):
        validation_prompt = f"""
Check if Indian Pincode {pincode} belongs to:
State: "{state}"
City: "{data.get("City")}"

Respond only in JSON with keys:
{{
  "state_valid": true/false,
  "expected_state": "<best guess state>",
  "city_valid": true/false,
  "expected_city": "<best guess city>"
}}
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": validation_prompt}],
                response_format={"type": "json_object"},
            )
            check = json.loads(response.choices[0].message.content)
        except Exception:
            check = {}

        # State validation
        if not check.get("state_valid", False):
            expected_state = check.get("expected_state", "")
            errors.append(f"Pincode-State mismatch (expected: {expected_state})")
            if expected_state:
                suggestions["State"] = expected_state

        # City validation
        if not check.get("city_valid", False):
            expected_city = check.get("expected_city", "")
            errors.append(f"Pincode-City mismatch (expected: {expected_city})")
            if expected_city:
                suggestions["City"] = expected_city

    return errors, suggestions


def extract_and_validate(input_text: str):
    prompt = f"""
You are an Indian Address Extractor.
Extract fields in JSON with exact keys:
- FullName
- HouseStreet
- Locality
- City
- State
- Pincode
- Phone
- Landmark
Text:
{input_text}
"""
    data = {}
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
        except Exception:
            data = {}

    # Fallback extraction with regex if OpenAI unavailable or failed
    if not data:
        # Basic regex-based extraction
        def grab(label):
            m = re.search(rf"{label}\s*:\s*(.*)", input_text, flags=re.IGNORECASE)
            return (m.group(1).strip() if m else "")

        data = {
            "FullName": grab("Full Name|FullName"),
            "HouseStreet": grab(r"HouseStreet|House No\.|House No|House|Street|Address"),
            "Locality": grab("Locality"),
            "City": grab("City"),
            "State": grab("State"),
            "Pincode": re.search(r"\b[1-9][0-9]{5}\b", input_text).group(0) if re.search(r"\b[1-9][0-9]{5}\b", input_text) else "",
            "Phone": normalize_phone(grab("Phone|Phone Number|Mobile|Contact")),
            "Landmark": grab("Landmark"),
        }
    errors, suggestions = validate_address_fields(data)
    return data, errors, suggestions


def analyze_address(input_text: str):
    return extract_and_validate(input_text)


def format_errors_for_user(errors: list[str]) -> str:
    if not errors:
        return ""
    bullet_list = "\n".join([f"- {e}" for e in errors])
    return (
        "I couldn't verify your address. Please correct these:\n"
        f"{bullet_list}\n\n"
        "Format reminder:\n"
        "Full Name:\nHouseStreet:\nLocality:\nCity:\nState:\nPincode (6 digits):\nPhone (10 digits):\nLandmark (Optional):"
    )


if __name__ == '__main__':
    input_text = """
    Full Name: Bogadi Bhargavi
    House No. + Street: 1-11
    Area / Locality: Kukatpally
    City: Hyderabad
    State: Telangana
    Pincode: 500072
    Phone Number: +91 6304742913
    Landmark: Near Forum Mall
    """
    data, errors, suggestions = extract_and_validate(input_text)
    print("Extracted:", json.dumps(data, indent=2))
    print("Errors:", errors)
    print("Suggestions:", suggestions)
    if errors:
        print(format_errors_for_user(errors))
