"""API hardening: slowapi throttling, security headers, audit hooks, PII-safe logs."""
from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.middleware.security_headers import SECURITY_HEADERS, SecurityHeadersMiddleware
from app.security.audit_logger import client_ip_from_request, log_security_event

__all__ = [
    "PIIScrubFilter",
    "SECURITY_HEADERS",
    "SecurityHeadersMiddleware",
    "api_rate_limit",
    "install_security",
    "limiter",
    "rate_limit_exceeded_handler",
    "scrub_pii",
]

# Phone (+91 / 10-digit), email, VIN (17 chars, no I/O/Q), Indian number plate.
_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"), "[VIN]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4}\b"), "[PLATE]"),
)


def scrub_pii(text: str) -> str:
    """Redact phone/email/VIN/plate patterns from a log line."""
    value = str(text)
    for pattern, replacement in _PII_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


class PIIScrubFilter(logging.Filter):
    """Logging filter applied to the root logger before handlers format records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub_pii(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {key: scrub_pii(value) for key, value in record.args.items()}
            else:
                record.args = tuple(scrub_pii(value) for value in record.args)
        return True


def _rate_key(request: Request) -> str:
    """Per client + optional session key; never reads request body."""
    session = request.headers.get("x-session-id") or request.query_params.get("session_id") or ""
    return f"{get_remote_address(request)}:{session}"


def api_rate_limit() -> str:
    """Dynamic limit value so tests and deployments can change it at runtime."""
    return f"{max(1, settings.API_RATE_LIMIT_PER_MIN)}/minute"


limiter = Limiter(key_func=_rate_key)


def _retry_after(exc: RateLimitExceeded) -> str:
    text = str(getattr(exc.limit, "limit", "")) if getattr(exc, "limit", None) else ""
    match = re.search(r"/(\d+)\s*(second|minute|hour)", text, re.IGNORECASE)
    if not match:
        return "60"
    amount, unit = int(match.group(1)), match.group(2).lower()
    return str(amount if unit == "second" else amount * 60 if unit == "minute" else amount * 3600)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 with a Retry-After header and no sensitive request details."""
    log_security_event(
        "RATE_LIMIT_EXCEEDED",
        client_ip=client_ip_from_request(request),
        endpoint=request.url.path,
        status=429,
        detail="slowapi_limit",
    )
    response = JSONResponse(
        status_code=429,
        content={"error": "Too many requests. Please wait before retrying."},
        headers={"Retry-After": _retry_after(exc)},
    )
    try:
        return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)
    except Exception:  # pragma: no cover - defensive, headers are optional
        return response


def install_security(app: FastAPI) -> None:
    """Register the limiter, headers, audit hooks and log scrubbing."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SecurityHeadersMiddleware)

    root = logging.getLogger()
    if not any(isinstance(item, PIIScrubFilter) for item in root.filters):
        root.addFilter(PIIScrubFilter())
