"""Pre-LLM PII masking and LLM output sanitisation.

Two deterministic helpers, no model and no network:

* :func:`mask_pii` replaces emails, phone numbers and 17-character VINs with
  fixed placeholders. It runs on every user-authored string before it reaches
  Groq, so the provider never receives the driver's contact details or VIN.
* :func:`sanitize_llm_output` strips script/style blocks, dangerous URI
  schemes and any residual HTML from a model reply before it is returned to
  the client (improper output handling).

Masking order matters: emails first, then VINs (a VIN contains a long digit
run), then phones, so a VIN is never partially consumed by the phone rule.
"""
from __future__ import annotations

import re

EMAIL_PLACEHOLDER = "[EMAIL_REDACTED]"
PHONE_PLACEHOLDER = "[PHONE_REDACTED]"
VIN_PLACEHOLDER = "[VIN_REDACTED]"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# 17 characters from the VIN alphabet (I, O and Q are excluded by ISO 3779).
_VIN_RE = re.compile(r"(?<![A-Za-z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9])")
# Indian mobile numbers, optionally with a +91 / 91 prefix.
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{9}(?!\d)")

# Blocks that must disappear with their content.
_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed|svg|math|link|meta|form)\b[^>]*>"
    r".*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_OPEN_BLOCK_RE = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|svg|math|link|meta|form)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^<>]{0,400}>")
_JS_URI_RE = re.compile(r"\b(?:javascript|vbscript|data\s*:\s*text/html)\s*:", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(r"\bon[a-z]{2,20}\s*=", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def mask_pii(text: str | None) -> str:
    """Replace emails, VINs and phone numbers with redaction placeholders."""
    if not text:
        return "" if text is None else str(text)
    value = str(text)
    value = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, value)
    value = _VIN_RE.sub(VIN_PLACEHOLDER, value)
    value = _PHONE_RE.sub(PHONE_PLACEHOLDER, value)
    return value


def contains_pii(text: str | None) -> bool:
    """True when the text still holds an unmasked email, VIN or phone."""
    if not text:
        return False
    value = str(text)
    return bool(
        _EMAIL_RE.search(value) or _VIN_RE.search(value) or _PHONE_RE.search(value)
    )


def mask_vin(vin: str | None) -> str:
    """Keep the last four characters of a VIN for display, hide the rest."""
    value = str(vin or "").strip()
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def mask_messages(messages) -> list[dict]:
    """Mask every non-system message before it is handed to the provider.

    The system prompt is left untouched: it carries the safety script and the
    public emergency number, which are not user PII.
    """
    masked: list[dict] = []
    for item in messages or ():
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        if role == "system":
            masked.append({"role": role, "content": content})
        else:
            masked.append({"role": role, "content": mask_pii(content)})
    return masked


def sanitize_llm_output(text: str | None) -> str:
    """Strip script blocks, event handlers and residual HTML from model text."""
    if not text:
        return "" if text is None else str(text)
    value = _CONTROL_RE.sub("", str(text))
    value = _BLOCK_RE.sub("", value)
    value = _OPEN_BLOCK_RE.sub("", value)
    value = _TAG_RE.sub("", value)
    value = _JS_URI_RE.sub("[blocked-scheme]:", value)
    value = _EVENT_ATTR_RE.sub("on_blocked=", value)
    return value.strip()


def sanitize_llm_list(values) -> list[str]:
    """Sanitise a list of model strings, dropping entries that become empty."""
    cleaned: list[str] = []
    for value in values or ():
        text = sanitize_llm_output(str(value))
        if text:
            cleaned.append(text)
    return cleaned
