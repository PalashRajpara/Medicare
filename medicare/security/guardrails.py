"""Pre-execution safety guardrails, prompt injection classifier, and healthcare safety boundaries."""

import base64
import codecs
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from medicare.config import settings
from medicare.config_loader import msg

logger = logging.getLogger(__name__)


def _resolve_config_path(filename: str) -> Path:
    """Resolve configuration file path."""
    config_dir = getattr(settings, "CONFIG_DIR", "config")
    p = Path(config_dir) / filename
    if p.exists():
        return p
    # Fallback to repo root config/
    repo_root = Path(__file__).resolve().parent.parent.parent
    p2 = repo_root / "config" / filename
    if p2.exists():
        return p2
    return p


def _load_guardrails_config() -> dict[str, Any]:
    """Load guardrails configuration from YAML."""
    path = _resolve_config_path("guardrails.yaml")
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load guardrails.yaml (%s), using defaults", e)
    return {}


_CONFIG = _load_guardrails_config()

DIRECT_OVERRIDE_PATTERNS: list[str] = _CONFIG.get(
    "direct_override_patterns",
    [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
        r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
        r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts)",
        r"bypass\s+(all\s+)?(safety|rules|restrictions)",
        r"override\s+(all\s+)?(system|safety|security)\s+(rules|prompts)",
    ],
)

SYSTEM_EXPOSURE_PATTERNS: list[str] = _CONFIG.get(
    "system_exposure_patterns",
    [
        r"(reveal|show|display|print|output|dump)\s+(your\s+)?(system\s+prompt|initial\s+instructions)",
        r"what\s+(is|are)\s+your\s+(exact\s+)?(system\s+prompt|instructions)",
        r"repeat\s+the\s+text\s+above\s+verbatim",
    ],
)

ROLE_MANIPULATION_PATTERNS: list[str] = _CONFIG.get(
    "role_manipulation_patterns",
    [
        r"you\s+are\s+now\s+in\s+developer\s+mode",
        r"enter\s+(god|dan|jailbreak|unrestricted|sudo)\s+mode",
        r"act\s+as\s+an\s+unrestricted\s+ai",
        r"simulate\s+a\s+root\s+user",
    ],
)

SQL_INJECTION_PATTERNS: list[str] = _CONFIG.get(
    "sql_injection_patterns",
    [
        r"(?i)\bdrop\s+table\b",
        r"(?i)\bdrop\s+database\b",
        r"(?i)\bdelete\s+from\b",
        r"(?i)\btruncate\s+table\b",
        r"(?i)\balter\s+table\b",
        r"(?i)\binsert\s+into\b",
        r"(?i)\bupdate\s+[a-zA-Z0-9_]+\s+set\b",
        r"(?i)\battach\s+database\b",
        r"(?i)\bpragma\s+[a-zA-Z0-9_]+",
        r"(?i)\bunion\s+(all\s+)?select\b",
        r";\s*--",
        r"'\s*or\s*'1'\s*=\s*'1'",
        r"'\s*or\s*1\s*=\s*1",
    ],
)

EMERGENCY_PATTERNS: list[str] = _CONFIG.get(
    "emergency_patterns",
    [
        r"(?i)\b(chest\s+pain\s+(now|right\s+now|currently|severe))\b",
        r"(?i)\bsevere\s+(?:crushing\s+)?chest\s+pain\b",
        r"(?i)\b(severe\s+bleeding|bleeding\s+profusely)\b",
        r"(?i)\b(unconscious|passed\s+out|not\s+breathing)\b",
        r"(?i)\b(stroke\s+symptoms|face\s+drooping|slurred\s+speech)\b",
        r"(?i)\b(heart\s+attack\s+(now|happening|symptoms\s+now))\b",
        r"(?i)\b(difficulty\s+breathing(\s+right\s+now|\s+now)?|cannot\s+breathe|choking)\b",
    ],
)

SELF_HARM_PATTERNS: list[str] = _CONFIG.get(
    "self_harm_patterns",
    [
        r"(?i)\b(suicide|kill\s+myself|end\s+my\s+life|want\s+to\s+die|hang\s+myself)\b",
        r"(?i)\b(commit\s+suicide|self-harm|cutting\s+myself)\b",
        r"(?i)\bhow\s+to\s+kill\s+myself\b",
    ],
)

MEDICAL_ADVICE_PATTERNS: list[str] = _CONFIG.get(
    "medical_advice_patterns",
    [
        r"(?i)\bwhat\s+medicine\s+should\s+i\s+take\b",
        r"(?i)\bprescribe\s+(me\s+)?(a\s+)?medicine\b",
        r"(?i)\bwhat\s+dosage\s+of\b",
        r"(?i)\bdo\s+i\s+have\s+cancer\b",
        r"(?i)\bdiagnose\s+my\b",
    ],
)

_pii_conf = _CONFIG.get("pii_patterns", {})
PII_PHONE_RE = re.compile(_pii_conf.get("phone", r"(?:(?:\+91|91)[-\s]?)?[6-9]\d{9}\b"))
PII_AADHAAR_RE = re.compile(
    _pii_conf.get("aadhaar", r"\b\d{4}[-\s]\d{4}[-\s]\d{4}\b|\b[2-9]\d{11}\b")
)
PII_PAN_RE = re.compile(_pii_conf.get("pan", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"))
PII_EMAIL_RE = re.compile(
    _pii_conf.get("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
)
PII_CLAIM_ID_RE = re.compile(
    _pii_conf.get("claim_id", r"\b(?:CLM|POL|CLAIM|POLICY|MED)[-_/][A-Za-z0-9]{5,}\b"),
    re.IGNORECASE,
)

_helplines = _CONFIG.get("helplines", {})
DEFAULT_HELPLINE_EMERGENCY = str(_helplines.get("emergency", "112"))
DEFAULT_HELPLINE_MENTAL_HEALTH = str(_helplines.get("mental_health", "Tele-MANAS 14416"))


@dataclass
class GuardrailResult:
    """Result of medicare safety guardrails evaluation."""

    blocked: bool = False
    category: str | None = None
    severity: str = "low"  # low, medium, high, critical
    message: str | None = None
    redacted_prompt: str = ""
    violations: list[str] = field(default_factory=list)
    has_medical_advice_boundary: bool = False


def redact_pii(text: str) -> str:
    """Redact Indian phone numbers, Aadhaar, PAN, emails, and claim IDs from text."""
    redacted = text
    redacted = PII_EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = PII_PAN_RE.sub("[REDACTED_PAN]", redacted)
    redacted = PII_AADHAAR_RE.sub("[REDACTED_AADHAAR]", redacted)
    redacted = PII_PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    redacted = PII_CLAIM_ID_RE.sub("[REDACTED_ID]", redacted)
    return redacted


def _detect_obfuscation(text: str) -> tuple[bool, str]:
    """Check for Base64 or ROT13 obfuscated injection attempts."""
    b64_matches = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", text)
    for b in b64_matches:
        try:
            decoded = base64.b64decode(b).decode("utf-8", errors="ignore")
            for pattern in DIRECT_OVERRIDE_PATTERNS + SYSTEM_EXPOSURE_PATTERNS:
                if re.search(pattern, decoded, re.IGNORECASE):
                    return True, "Obfuscation Attacks (Base64)"
        except Exception:
            pass

    try:
        rot13_decoded = codecs.decode(text, "rot_13")
        for pattern in DIRECT_OVERRIDE_PATTERNS:
            if re.search(pattern, rot13_decoded, re.IGNORECASE):
                return True, "Obfuscation Attacks (ROT13)"
    except Exception:
        pass

    return False, ""


def evaluate_guardrails(prompt: str) -> tuple[bool, list[str]]:
    """Evaluate an input prompt for safety violations.

    Returns:
        (is_safe, violations_list)
    """
    violations: list[str] = []

    for pattern in DIRECT_OVERRIDE_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            violations.append("Direct Override")
            break

    for pattern in SYSTEM_EXPOSURE_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            violations.append("System Exposure")
            break

    for pattern in ROLE_MANIPULATION_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            violations.append("Role Manipulation")
            break

    is_obfuscated, obf_type = _detect_obfuscation(prompt)
    if is_obfuscated:
        violations.append(obf_type)

    is_safe = len(violations) == 0
    return is_safe, violations


def check_medicare_guardrails(prompt: str) -> GuardrailResult:
    """Full guardrail check for MediCare Navigator:
    1. Base prompt injection
    2. SQL injection patterns in natural language input
    3. Self-harm / crisis detection
    4. Medical emergency advisory
    5. PII redaction
    6. Medical advice boundary detection
    """
    redacted = redact_pii(prompt)
    violations: list[str] = []

    # 1. Base Prompt Injections
    is_safe, injection_viols = evaluate_guardrails(prompt)
    if not is_safe:
        return GuardrailResult(
            blocked=True,
            category="prompt_injection",
            severity="high",
            message=msg("prompt_injection_refusal"),
            redacted_prompt=redacted,
            violations=injection_viols,
        )

    # 2. Self-Harm Detection (Critical - Immediate helpline response)
    for pattern in SELF_HARM_PATTERNS:
        if re.search(pattern, prompt):
            return GuardrailResult(
                blocked=True,
                category="self_harm",
                severity="critical",
                message=msg("crisis_refusal"),
                redacted_prompt=redacted,
                violations=["Self-Harm / Crisis"],
            )

    # 3. Medical Emergency (Critical - Direct to ER / 112)
    for pattern in EMERGENCY_PATTERNS:
        if re.search(pattern, prompt):
            return GuardrailResult(
                blocked=True,
                category="medical_emergency",
                severity="critical",
                message=msg("emergency_refusal"),
                redacted_prompt=redacted,
                violations=["Medical Emergency"],
            )

    # 4. Destructive / Stacked SQL Injection in natural language prompt
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, prompt):
            return GuardrailResult(
                blocked=True,
                category="sql_injection",
                severity="critical",
                message=msg("sql_injection_refusal"),
                redacted_prompt=redacted,
                violations=["SQL Injection Attempt"],
            )

    # 5. Check if PII was detected
    has_pii = redacted != prompt
    if has_pii:
        violations.append("PII Redacted")

    # 6. Soft Medical Advice Boundary
    has_medical_boundary = False
    for pattern in MEDICAL_ADVICE_PATTERNS:
        if re.search(pattern, prompt):
            has_medical_boundary = True
            violations.append("Medical Advice Boundary")
            break

    return GuardrailResult(
        blocked=False,
        category=None,
        severity="low",
        message=None,
        redacted_prompt=redacted,
        violations=violations,
        has_medical_advice_boundary=has_medical_boundary,
    )
