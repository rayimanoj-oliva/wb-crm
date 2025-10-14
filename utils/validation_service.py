from __future__ import annotations

import os
import re
import requests
import json
from typing import Dict, Any, Optional


class ValidationService:
    """Service for validating names and phone numbers with OpenAI integration and fallback validation."""
    
    @staticmethod
    def validate_name_with_openai(name: str) -> Dict[str, Any]:
        """Validate a name using OpenAI API with fallback to basic validation."""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return ValidationService._fallback_name_validation(name)
            
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            
            prompt = (
                "You are a name validator. Check if the given text is a valid human first name.\n"
                "A valid first name should:\n"
                "- Be at least 3 letters long\n"
                "- Contain only letters, hyphens, or apostrophes\n"
                "- Look like a real human name (not gibberish like 'asdf')\n"
                "- Have a mix of vowels and consonants\n\n"
                "Return ONLY JSON with: {\"valid\": true/false, \"name\": \"extracted_name\"}\n"
                "If valid, return the cleaned first name. If invalid, return null for name."
            )
            
            data = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Validate this first name: {name}"}
                ]
            }
            
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                result = json.loads(content)
                
                if result.get("valid") and result.get("name"):
                    first_name = result.get("name").strip()
                    if len(first_name) >= 3:
                        return {"valid": True, "name": first_name}
            
            # If OpenAI fails or returns invalid, fall back to basic validation
            return ValidationService._fallback_name_validation(name)
            
        except Exception:
            # Fallback to basic validation if OpenAI fails
            return ValidationService._fallback_name_validation(name)
    
    @staticmethod
    def _fallback_name_validation(name: str) -> Dict[str, Any]:
        """Fallback name validation using regex patterns."""
        try:
            if not isinstance(name, str):
                return {"valid": False, "name": None}
            
            name = name.strip()
            if not name:
                return {"valid": False, "name": None}
            
            # Check for digits
            if re.search(r"\d", name):
                return {"valid": False, "name": None}
            
            # Check for invalid characters
            if re.search(r"[^A-Za-z\- '\s]", name):
                return {"valid": False, "name": None}
            
            letters_only = re.sub(r"[^A-Za-z]", "", name)
            if len(letters_only) < 3:
                return {"valid": False, "name": None}
            
            # Check for vowels and consonants
            if not re.search(r"[AEIOUaeiou]", letters_only):
                return {"valid": False, "name": None}
            
            if not re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only):
                return {"valid": False, "name": None}
            
            # Check for repeated characters
            if len(set(letters_only.lower())) == 1:
                return {"valid": False, "name": None}
            
            if re.search(r"(.)\1{3,}", letters_only, flags=re.IGNORECASE):
                return {"valid": False, "name": None}
            
            # Check blacklist
            blacklist = {"test", "testing", "asdf", "qwerty", "user", "customer", "name", "unknown", "oliva", "clinic", "abc"}
            if name.strip().lower() in blacklist:
                return {"valid": False, "name": None}
            
            # Extract first token (first name)
            first_token = (re.findall(r"[A-Za-z][A-Za-z\-']+", name) or [""])[0]
            if len(first_token) >= 3:
                return {"valid": True, "name": first_token.strip()}
            
            return {"valid": False, "name": None}
            
        except Exception:
            return {"valid": False, "name": None}
    
    @staticmethod
    def validate_phone_number(phone_text: str) -> Optional[str]:
        """Validate and normalize Indian phone number."""
        try:
            if not isinstance(phone_text, str):
                return None
            
            # Extract digits only
            digits = re.sub(r"\D", "", phone_text)
            
            # Check minimum length
            if len(digits) < 10:
                return None
            
            # Get last 10 digits
            last10 = digits[-10:]
            if len(last10) != 10:
                return None
            
            # Return normalized format
            return f"+91{last10}"
            
        except Exception:
            return None
    
    @staticmethod
    def looks_like_first_name(candidate: str) -> bool:
        """Check if text looks like a valid first name using basic patterns."""
        try:
            if not isinstance(candidate, str):
                return False
            
            name = candidate.strip()
            if not name:
                return False
            
            # Check for digits
            if re.search(r"\d", name):
                return False
            
            # Check for invalid characters
            if re.search(r"[^A-Za-z\- '\s]", name):
                return False
            
            letters_only = re.sub(r"[^A-Za-z]", "", name)
            if len(letters_only) < 3:
                return False
            
            # Check for vowels and consonants
            if not re.search(r"[AEIOUaeiou]", letters_only):
                return False
            
            if not re.search(r"[B-DF-HJ-NP-TV-Zb-df-hj-np-tv-z]", letters_only):
                return False
            
            # Check for repeated characters
            if len(set(letters_only.lower())) == 1:
                return False
            
            if re.search(r"(.)\1{3,}", letters_only, flags=re.IGNORECASE):
                return False
            
            # Check blacklist
            blacklist = {"test", "testing", "asdf", "qwerty", "user", "customer", "name", "unknown", "oliva", "clinic", "abc"}
            if name.strip().lower() in blacklist:
                return False
            
            # Extract first token
            first_token = (re.findall(r"[A-Za-z][A-Za-z\-']+", name) or [""])[0]
            return len(first_token) >= 3
            
        except Exception:
            return False
