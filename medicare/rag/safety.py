"""Safety mechanisms for detecting indirect prompt injections in retrieved chunks."""

import base64
import re

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous)\s+rules", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"reveal\s+your\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"what\s+are\s+your\s+instructions", re.IGNORECASE),
    re.compile(r"output\s+the\s+secret", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|system\|>", re.IGNORECASE),
    re.compile(r"act\s+as\s+(an?\s+)?unrestricted\s+ai", re.IGNORECASE),
]


def detect_injection(text: str) -> tuple[bool, str | None]:
    """Inspect text for instruction injection, role overrides, or obfuscated payloads.

    Returns:
        (is_injected, matched_pattern_or_reason)
    """
    if not text:
        return False, None

    # Check direct patterns
    for pat in INJECTION_PATTERNS:
        match = pat.search(text)
        if match:
            return True, f"Matched instruction override pattern: {match.group(0)}"

    # Check base64 obfuscation >= 28 chars
    b64_matches = re.findall(r"[A-Za-z0-9+/=]{28,}", text)
    for token in b64_matches:
        try:
            decoded = base64.b64decode(token).decode("utf-8", errors="ignore")
            for pat in INJECTION_PATTERNS:
                if pat.search(decoded):
                    return True, "Obfuscated Base64 instruction override detected"
        except Exception:
            pass

    return False, None


def sanitize_text(text: str) -> str:
    """Normalize whitespace and strip null bytes."""
    if not text:
        return ""
    text = text.replace("\x00", "")
    return re.sub(r"[ \t]+", " ", text).strip()
