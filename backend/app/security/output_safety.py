"""Safety-critical output override and hidden-context leak blocker.

Runs AFTER deterministic rules, ML or Groq. A model can never talk a driver
into continuing with a brake/oil-pressure/overheat/airbag hazard, and an LLM
cannot echo system-prompt markers back to the client.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.security.image_sanitizer import CRITICAL_VISION_LABELS, VisionLabel

STOP_AND_TOW = (
    "DO NOT DRIVE. Stop in a safe location, switch off the engine, arrange a "
    "tow, and call +91 6392077642."
)

_CRITICAL_TEXT_RULES: tuple[tuple[re.Pattern[str], VisionLabel], ...] = (
    (re.compile(r"brake\s*(failure|fail|fluid|pedal\s*to\s*the\s*floor)|no\s*brakes|loss\s*of\s*brakes", re.I), VisionLabel.BRAKE_FAILURE),
    (re.compile(r"oil\s*(pressure|leak)|low\s*engine\s*oil", re.I), VisionLabel.OIL_PRESSURE),
    (re.compile(r"overheat|steam\s*from\s*(the\s*)?bonnet|temperature\s*(gauge\s*)?in\s*the\s*red", re.I), VisionLabel.ENGINE_OVERHEAT),
    (re.compile(r"airbag|srs\s*(warning|light)|\babs\s*(light|failure|warning)\b", re.I), VisionLabel.AIRBAG_ABS),
)

# Advice that must never survive a safety-critical flag.
_UNSAFE_ADVICE_RE = re.compile(
    r"[^.!\n]*\b(continue|keep|carry\s+on)\s+(driving|to\s+drive|on\s+driving)|"
    r"[^.!\n]*\b(safe\s+to|okay\s+to|fine\s+to)\s+drive|"
    r"[^.!\n]*\bdrive\s+(slowly|gently|on|home|to\s+the|to\s+a)\b|"
    r"[^.!\n]*\b(bypass|disable|disconnect|remove|ignore)\b[^.!\n]*\b(sensor|airbag|abs|brake|warning\s+light|srs)\b|"
    r"[^.!\n]*\breset\b[^.!\n]*\b(warning\s+light|fault\s+code)\b",
    re.IGNORECASE,
)

_SYSTEM_MARKER_RE = re.compile(
    r"SYSTEM\s*:|You\s+are\s+IM\s+Buddy|DIAGNOSIS_SCHEMA_HINT|"
    r"SYSTEM_MECHANIC|INTERNAL\s+(POLICY|RULE|PROMPT)|"
    r"ORDER_SNAPSHOT|warning_light_id=" ,
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OutputGuardResult:
    payload: dict
    hazards: tuple[VisionLabel, ...]
    removed_unsafe_advice: int
    redacted_hidden_context: int


def hazards_from_text(text: str) -> set[VisionLabel]:
    """Detect explicitly mentioned critical hazards in free text."""
    value = text or ""
    return {label for pattern, label in _CRITICAL_TEXT_RULES if pattern.search(value)}


def hazards_from_context(context: str) -> set[VisionLabel]:
    """Read enum markers emitted by the vision adapter (no free text)."""
    found: set[VisionLabel] = set()
    for value in re.findall(r"warning_light_id[=:]([a-z_]+)", context or ""):
        enum = VisionLabel.__members__.get(value.upper())
        if enum is not None:
            found.add(enum)
    return found & set(CRITICAL_VISION_LABELS)


def scrub_hidden_context(text: str) -> tuple[str, int]:
    """Remove leaked system-prompt markers, counting redactions."""
    if not text:
        return text, 0
    cleaned, count = _SYSTEM_MARKER_RE.subn("[redacted]", str(text))
    return cleaned, count


def scrub_unsafe_advice(text: str) -> tuple[str, int]:
    """Delete sentences that recommend driving on or bypassing safety systems."""
    if not text:
        return text, 0
    cleaned, count = _UNSAFE_ADVICE_RE.subn("", str(text))
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, count


def _scrub_list(values: object) -> tuple[list[str], int]:
    if not isinstance(values, (list, tuple)):
        return [], 0
    cleaned: list[str] = []
    removed = 0
    for value in values:
        text, hits = scrub_unsafe_advice(str(value))
        removed += hits
        if text:
            cleaned.append(text)
    return cleaned, removed


def apply_output_guard(
    payload: dict,
    *,
    hazards: set[VisionLabel] | None = None,
    llm_text: str | None = None,
) -> OutputGuardResult:
    """Enforce stop/tow guidance and scrub hidden context in a diagnosis dict.

    ``payload`` is never mutated; a sanitized copy is returned.
    """
    result = dict(payload or {})
    active_hazards = set(hazards or ())
    removed = 0
    redacted = 0

    for key in ("summary", "drive_guidance", "safety_warning", "next_steps", "possible_causes"):
        if key in ("next_steps", "possible_causes"):
            result[key], hits = _scrub_list(result.get(key))
            removed += hits
        else:
            result[key], hits = scrub_unsafe_advice(result.get(key, ""))
            removed += hits
        if isinstance(result[key], str):
            result[key], hits = scrub_hidden_context(result[key])
            redacted += hits

    if llm_text:
        _, hits = scrub_hidden_context(llm_text)
        redacted += hits

    if active_hazards:
        result["urgency"] = "critical"
        result["drive_guidance"] = STOP_AND_TOW
        warning = scrub_hidden_context(str(result.get("safety_warning") or ""))[0]
        result["safety_warning"] = (
            (warning + " " if warning else "")
            + "Safety-critical hazard flagged ("
            + ", ".join(sorted(item.value for item in active_hazards))
            + "). "
            + STOP_AND_TOW
        )
        result["inspection_recommended"] = True

    return OutputGuardResult(
        result,
        tuple(sorted(active_hazards, key=lambda item: item.value)),
        removed,
        redacted,
    )
