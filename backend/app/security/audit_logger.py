"""Structured security-event logging (one JSON object per line).

Stateless design: events carry only metadata. Image bytes, Groq keys, JWTs and
unmasked PII are never accepted or echoed. Every field is redacted before the
line is written, so a caller cannot smuggle a phone number into the audit log.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.security.pii_masker import mask_pii

AUDIT_LOGGER_NAME = "app.security.audit"
AUDIT_LOGGER = logging.getLogger(AUDIT_LOGGER_NAME)

# The three event types produced by the stateless hardening layer.
SECURITY_EVENTS = frozenset(
    {
        "PROMPT_INJECTION_BLOCKED",
        "INVALID_UPLOAD",
        "RATE_LIMIT_EXCEEDED",
    }
)

_MAX_DETAIL = 300
_MAX_FIELD = 200

_file_handler: logging.Handler | None = None
_file_path: str = ""


def _secret_values() -> tuple[str, ...]:
    """Values that must never appear in an audit line."""
    values: list[str] = []
    for name in ("GROQ_API_KEY",):
        value = str(getattr(settings, name, "") or "")
        if len(value) >= 8:
            values.append(value)
    return tuple(values)


def redact(value: Any) -> str:
    """Mask PII and configured secrets, then bound the field length."""
    text = "" if value is None else str(value)
    text = mask_pii(text)
    for secret in _secret_values():
        text = text.replace(secret, "[REDACTED]")
    return text[:_MAX_DETAIL]


def _ensure_file_handler() -> None:
    """Attach an optional JSON file sink when SECURITY_AUDIT_LOG is set."""
    global _file_handler, _file_path
    path = str(getattr(settings, "SECURITY_AUDIT_LOG", "") or "").strip()
    if not path:
        return
    resolved = str(Path(path).expanduser().resolve())
    if _file_handler is not None and _file_path == resolved:
        return
    if _file_handler is not None:
        AUDIT_LOGGER.removeHandler(_file_handler)
        _file_handler.close()
    try:
        Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(resolved, encoding="utf-8")
    except OSError:  # pragma: no cover - unwritable path is a deployment issue
        AUDIT_LOGGER.warning("Security audit file sink unavailable.")
        _file_handler, _file_path = None, ""
        return
    handler.setFormatter(logging.Formatter("%(message)s"))
    AUDIT_LOGGER.addHandler(handler)
    _file_handler, _file_path = handler, resolved


def log_security_event(
    event_type: str,
    *,
    client_ip: str = "",
    endpoint: str = "",
    status: int | None = None,
    detail: str = "",
) -> dict:
    """Emit one structured security event and return the dict that was logged."""
    event = {
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "event_type": redact(event_type)[:_MAX_FIELD],
        "client_ip": redact(client_ip)[:_MAX_FIELD],
        "endpoint": redact(endpoint)[:_MAX_FIELD],
        "status": int(status) if status is not None else None,
        "detail": redact(detail),
    }
    _ensure_file_handler()
    AUDIT_LOGGER.info(json.dumps(event, ensure_ascii=False, default=str))
    return event


def client_ip_from_request(request: Any) -> str:
    """Best-effort client address; proxy headers are not trusted by default."""
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "")


__all__ = [
    "SECURITY_EVENTS",
    "client_ip_from_request",
    "log_security_event",
    "redact",
]
