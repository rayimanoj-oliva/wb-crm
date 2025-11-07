from __future__ import annotations

import os
import re
import requests
from typing import Dict


def _looks_like_human_name(name: str | None) -> bool:
    """Heuristic validation for a plausible human name."""
    if not isinstance(name, str):
        return False
    candidate = name.strip()
    if not candidate:
        return False

    # Only letters, spaces, hyphens, apostrophes
    if re.search(r"[^A-Za-z\s\-']", candidate):
        return False

    # Must have at least 3 alphabetic chars
    letters_only = re.sub(r"[^A-Za-z]", "", candidate)
    if len(letters_only) < 3:
        return False

    # Must contain both vowel and consonant
    if not re.search(r"[AEIOUaeiou]", letters_only):
        return False
    if not re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only):
        return False

    # Reject too many consecutive consonants or vowels
    if re.search(r"[B-DF-HJ-NP-TV-Z]{4,}", candidate, re.IGNORECASE):
        return False
    if re.search(r"[AEIOU]{4,}", candidate, re.IGNORECASE):
        return False

    # Disallow gibberish substrings like "asdf", "qwer", etc.
    gibberish_patterns = ["asdf", "qwer", "zxcv", "hjkl", "ghjk", "lkjh", "poiuy", "mnbv"]
    lowered = candidate.lower()
    if any(pat in lowered for pat in gibberish_patterns):
        return False

    # Disallow all same letters or extreme repetition
    if len(set(letters_only.lower())) == 1:
        return False
    if re.search(r"(.)\1{3,}", letters_only, re.IGNORECASE):
        return False

    # Token structure checks
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", candidate)
    if not tokens:
        return False
    if len(tokens) >= 2:
        # Ensure first two tokens are at least 2 characters
        if any(len(re.sub(r"[^A-Za-z]", "", t)) < 2 for t in tokens[:2]):
            return False
    else:
        # Single name must be at least 3 letters
        if len(letters_only) < 3:
            return False

    # Common placeholders/brand words blacklist
    blacklist = {
        "test", "testing", "asdf", "qwerty", "user", "customer", "name",
        "unknown", "oliva", "clinic", "abc", "demo", "sample"
    }
    if lowered in blacklist:
        return False

    # Allow some common Indian name patterns (optional enhancement)
    indian_name_whitelist = [
        "mohammed", "kumar", "sree", "sri", "anil", "raj", "ravi", "venkat",
        "suresh", "priya", "anita", "arun", "deepak", "meenakshi", "nisha",
        "swathi", "sandeep", "rajesh", "ganesh"
    ]
    for pat in indian_name_whitelist:
        if pat in lowered:
            return True

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
                "- Reject placeholders like 'test', 'user', 'asdfghjkl', 'qwerty', etc.\n\n"
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
                    # Combine OpenAI and local check
                    name_out = (result.get("name") or candidate_name or "").strip()
                    valid_flag = bool(result.get("valid")) and _looks_like_human_name(name_out)
                    return {
                        "valid": valid_flag,
                        "name": name_out if valid_flag else None,
                        "reason": result.get("reason")
                        or ("validated" if valid_flag else "not a plausible name"),
                    }
                except Exception:
                    pass
        except Exception:
            pass

    # Local fallback (offline mode)
    name_out = candidate_name.strip()
    if _looks_like_human_name(name_out):
        return {"valid": True, "name": name_out, "reason": "local_fallback"}
    return {"valid": False, "name": None, "reason": "local_reject"}