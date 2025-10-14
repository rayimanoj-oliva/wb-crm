from __future__ import annotations

import os
import re
import requests
from typing import Dict


def _looks_like_human_name(name: str | None) -> bool:
    if not isinstance(name, str):
        return False
    candidate = name.strip()
    if not candidate:
        return False
    # Reject digits and disallow characters other than letters, spaces, hyphens, apostrophes
    if re.search(r"\d", candidate):
        return False
    if re.search(r"[^A-Za-z\- '\s]", candidate):
        return False
    letters_only = re.sub(r"[^A-Za-z]", "", candidate)
    if len(letters_only) < 3:
        return False
    # Must contain at least one vowel and one consonant
    if not re.search(r"[AEIOUaeiou]", letters_only):
        return False
    if not re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only):
        return False
    # Disallow all same character or long repeats
    if len(set(letters_only.lower())) == 1:
        return False
    if re.search(r"(.)\1{3,}", letters_only, flags=re.IGNORECASE):
        return False
    # Token structure: allow full name or first name; prefer first two tokens >= 2 letters each
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", candidate)
    if len(tokens) >= 2:
        if any(len(re.sub(r"[^A-Za-z]", "", t)) < 2 for t in tokens[:2]):
            return False
    else:
        if len(letters_only) <= 3:
            return False
    # Common non-name placeholders/brand terms
    blacklist = {
        "test", "testing", "asdf", "qwerty", "user", "customer", "name", "unknown", "oliva", "clinic", "abc"
    }
    if candidate.strip().lower() in blacklist:
        return False
    return True


def validate_human_name(text: str) -> Dict[str, object]:
    """Validate that the input text is a plausible human name.

    Returns dict: { valid: bool, name: str|None, reason: str }
    - Accepts full name or first name
    - Uses OpenAI when available, with local heuristic fallback
    """
    text = (text or "").strip()
    # Extract potential name tokens from text
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", text)
    candidate_name = " ".join(tokens[:3]) if tokens else text

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            prompt = (
                "You are a strict validator for human names. Check if the text is a plausible human name.\n"
                "Rules:\n"
                "- Accept full name or first name.\n"
                "- At least 3 alphabetic characters total.\n"
                "- Only letters, spaces, hyphens, apostrophes.\n"
                "- Must look like a real name (has vowels and consonants, not gibberish).\n"
                "- Reject placeholders like 'test', 'user'.\n\n"
                "Return ONLY JSON: {\"valid\": true|false, \"name\": string|null, \"reason\": string}."
            )
            data = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Validate this name: {candidate_name}"},
                ],
            }
            resp = requests.post(url, headers=headers, json=data, timeout=12)
            if resp.status_code == 200:
                try:
                    content = resp.json()["choices"][0]["message"]["content"]
                    import json as _json
                    result = _json.loads(content)
                    # Enforce local sanity too
                    name_out = (result.get("name") or candidate_name or "").strip()
                    valid_flag = bool(result.get("valid")) and _looks_like_human_name(name_out)
                    return {"valid": valid_flag, "name": name_out if valid_flag else None, "reason": result.get("reason") or ("validated" if valid_flag else "not a plausible name")}
                except Exception:
                    pass
        except Exception:
            pass

    # Local fallback
    name_out = candidate_name.strip()
    if _looks_like_human_name(name_out):
        return {"valid": True, "name": name_out, "reason": "local_fallback"}
    return {"valid": False, "name": None, "reason": "local_reject"}


