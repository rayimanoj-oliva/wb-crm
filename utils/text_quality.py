import re


_VOWELS_RE = re.compile(r"[aeiouAEIOU]")
_ALPHA_RE = re.compile(r"^[a-zA-Z]+$")


def is_nonsensical(text: str) -> bool:
    """
    Heuristic gibberish detector for short WhatsApp texts.

    Returns True when the text is likely random letters or contains no meaningful words.
    - Only flags short alphabetic strings with few/no vowels or obvious keyboard-mash patterns
    - Allows common short words and typical chat tokens
    - Intended to run before greeting/welcome flow
    """
    if not text:
        return False

    t = (text or "").strip()

    # Ignore long messages; assume they are meaningful enough
    if len(t) > 120:
        return False

    # Allowlist common short tokens (fast path)
    allow = {
        "hi", "hello", "hlo", "ok", "okay", "thanks", "thankyou", "thank you",
        "yes", "no", "call", "clinic", "doctor", "address", "payment",
        "appointment", "book", "order", "help",
    }
    if t.lower() in allow:
        return False

    # Strip non-letters for core checks
    letters_only = re.sub(r"[^a-zA-Z]", "", t)
    if not letters_only:
        return False

    # Very short pure-letter tokens with no vowels → likely gibberish
    if _ALPHA_RE.match(t) and len(t) >= 4 and not _VOWELS_RE.search(t):
        return True

    # Keyboard-mash like repetitions (e.g., "hhhh", "jjjjj")
    if len(set(letters_only)) == 1 and len(letters_only) >= 4:
        return True

    # Low vowel ratio in pure-letter strings (heuristic)
    if _ALPHA_RE.match(letters_only) and len(letters_only) >= 5:
        vowel_count = len(_VOWELS_RE.findall(letters_only))
        if vowel_count <= 1:
            return True

    return False


