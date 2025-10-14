import os
import re
import requests


def _normalize_indian_phone(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    digits = re.sub(r"\D", "", text or "")
    if len(digits) < 10:
        return None
    last10 = digits[-10:]
    if len(last10) != 10:
        return None
    # Basic Indian mobile validity: commonly starts with 6/7/8/9 (soft check)
    if not re.match(r"[6-9]", last10[0]):
        pass
    return "+91" + last10


def validate_indian_phone(text: str) -> dict[str, object]:
    """Validate Indian mobile number.

    Returns: { valid: bool, phone: str|None, reason: str }
    - Normalizes to +91XXXXXXXXXX
    - Uses OpenAI if available, otherwise local fallback
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            prompt = """You validate Indian mobile numbers. Extract a phone from the text and validate it.
Rules:
- Must be exactly 10 digits (Indian mobile).
- Allow +91 prefix or separators, but final result must be +91XXXXXXXXXX (10 digits).

Return ONLY JSON: {"valid": true|false, "phone": string|null, "reason": string}."""
            data = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Validate this phone: {text}"},
                ],
            }
            resp = requests.post(url, headers=headers, json=data, timeout=12)
            if resp.status_code == 200:
                try:
                    content = resp.json()["choices"][0]["message"]["content"]
                    import json as _json
                    result = _json.loads(content)
                    phone_out = _normalize_indian_phone(result.get("phone") or text)
                    valid_flag = bool(result.get("valid")) and bool(phone_out)
                    return {
                        "valid": valid_flag,
                        "phone": phone_out if valid_flag else None,
                        "reason": result.get("reason") or ("validated" if valid_flag else "invalid"),
                    }
                except Exception:
                    pass
        except Exception:
            pass

    # Local fallback
    phone_out = _normalize_indian_phone(text)
    if phone_out:
        return {"valid": True, "phone": phone_out, "reason": "local_fallback"}
    return {"valid": False, "phone": None, "reason": "local_reject"}
