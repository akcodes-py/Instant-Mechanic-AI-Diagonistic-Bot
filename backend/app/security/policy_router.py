"""Deterministic policy router and bounded-context builder.

Ported from ShopAssist's ``SupportCopilot`` / ``SupportPipeline`` patterns and
adapted to automotive diagnostics:

* clear warning light or a single high-confidence classifier match is served
  from a deterministic template (zero LLM tokens);
* wide MAPIE conformal sets or missing vehicle context produce structured HITL
  follow-up questions (zero LLM tokens);
* only ambiguous multi-symptom synthesis reaches Groq, with a bounded history,
  bounded snippets and a server-side token ceiling.

The sufficiency check is deliberately non-circular: it never treats the
classifier's own proposed label as evidence that the input was sufficient. It
only inspects conformal set size, explicit vehicle fields and observed labels.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from app.config import settings
from app.security.image_sanitizer import VisionObservation, map_label
from app.security.injection_guard import GuardResult, sanitize_message, sanitize_thread
from app.services.triage import find_rule

_VISION_MARKER = "Reliable dashboard warning lights detected:"


class Route(str, Enum):
    TEMPLATE = "deterministic_template"
    HITL = "hitl_follow_up"
    LLM = "bounded_llm"


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str
    template: str = ""
    follow_ups: tuple[str, ...] = ()
    max_tokens: int = 0
    estimated_context_tokens: int = 0


@dataclass(frozen=True)
class BoundedContext:
    text: str
    messages_used: int
    estimated_tokens: int


@dataclass(frozen=True)
class Sufficiency:
    sufficient: bool
    missing: tuple[str, ...]
    prediction_set_size: int | None = None


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate (chars/4) for local budgeting.

    This is an estimate, not a provider tokenizer. It is used only for caps and
    for the before/after benchmark, which reports it as an estimate.
    """
    return int(math.ceil(len(text or "") / 4.0))


def enum_only_history_line(content: str) -> str:
    """Replace raw detector labels in a stored history line with enums only.

    Chat history is plain text, so this rebuilds just the vision line before it
    is handed to the model. Filenames and OCR text are never copied forward.
    """
    if _VISION_MARKER not in (content or ""):
        return content or ""
    prefix, rest = content.split(_VISION_MARKER, 1)
    labels = rest.split(".", 1)[0]
    mapped = {
        enum.value
        for enum in (map_label(part.strip()) for part in re.split(r",|\band\b", labels))
        if enum is not None
    }
    if not mapped:
        return prefix + "No reliable warning-light labels were detected."
    return prefix + "; ".join(f"warning_light_id={value}" for value in sorted(mapped)) + "."


def build_bounded_context(
    messages: Iterable[dict],
    latest: str = "",
    *,
    max_messages: int | None = None,
    max_chars: int | None = None,
    max_tokens: int | None = None,
) -> BoundedContext:
    """Sanitize every turn, cap history and apply a hard token ceiling."""
    cap_messages = max_messages or settings.MAX_GUARD_HISTORY_MESSAGES
    cap_chars = max_chars or settings.MAX_GUARD_CONTEXT_CHARS
    cap_tokens = max_tokens or settings.MAX_GUARD_CONTEXT_TOKENS

    parts: list[str] = []
    used = 0
    for message in sanitize_thread(messages):
        line = f"{message['role']}: {enum_only_history_line(message['content'])}"
        if estimate_tokens(" ".join(parts + [line])) > cap_tokens:
            break
        parts.append(line)
        used += 1
        if sum(len(part) for part in parts) >= cap_chars:
            break

    if latest:
        guard = sanitize_message(latest)
        if not guard.blocked and guard.text:
            parts.append(f"user: {guard.text}")

    text = "\n".join(parts)
    if len(text) > cap_chars:
        text = text[:cap_chars].rsplit(" ", 1)[0]
    return BoundedContext(text, used, estimate_tokens(text))


def check_sufficiency(
    *,
    conformal_result: dict | None = None,
    vehicle: dict | str | None = None,
    symptom: str = "",
    vision_observations: Iterable[VisionObservation] = (),
) -> Sufficiency:
    """Non-circular sufficiency gate connected to MAPIE conformal prediction."""
    missing: list[str] = []
    set_size: int | None = None
    if conformal_result is not None:
        try:
            set_size = int(conformal_result.get("set_size", 0))
        except (TypeError, ValueError):
            set_size = 0
        if set_size > 2 or set_size <= 0:
            missing.append("wide_or_empty_conformal_prediction_set")

    if isinstance(vehicle, dict):
        has_vehicle = any(str(value or "").strip() for value in vehicle.values())
    else:
        has_vehicle = bool(str(vehicle or "").strip())
    if not has_vehicle:
        missing.append("vehicle_make_model")

    if len((symptom or "").split()) < 3 and not list(vision_observations or ()):
        missing.append("symptom_detail")

    return Sufficiency(not missing, tuple(missing), set_size)


def route(
    symptom: str,
    *,
    history: Iterable[dict] = (),
    vision_observations: Iterable[VisionObservation] = (),
    conformal_result: dict | None = None,
    nlp_confidence: float = 0.0,
    vehicle: dict | str | None = None,
) -> RouteDecision:
    """Choose one of three deterministic routes. Never calls a model itself."""
    guard: GuardResult = sanitize_message(symptom)
    context = build_bounded_context(history, symptom)
    max_tokens = min(settings.MAX_LLM_TOKENS, 800)

    if guard.blocked:
        return RouteDecision(
            Route.HITL,
            "injection_blocked",
            follow_ups=("Please describe only the vehicle symptom in your own words.",),
            max_tokens=0,
            estimated_context_tokens=0,
        )

    observations = list(vision_observations)
    distinct_labels = {item.warning_light_id for item in observations}
    clear_vision = len(distinct_labels) == 1 and any(
        item.confidence >= settings.VISION_CONF for item in observations
    )
    set_size = None
    if conformal_result is not None:
        try:
            set_size = int(conformal_result.get("set_size", 0))
        except (TypeError, ValueError):
            set_size = 0
    single_high_confidence = nlp_confidence >= 0.7 and set_size == 1

    rule = find_rule(guard.text)
    if clear_vision or single_high_confidence:
        template = ""
        if rule and isinstance(rule.get("diagnosis"), dict):
            template = str(rule["diagnosis"].get("summary") or "")
        return RouteDecision(
            Route.TEMPLATE,
            "clear_warning_light_or_single_high_confidence_match",
            template=template,
            max_tokens=0,
            estimated_context_tokens=0,
        )

    sufficiency = check_sufficiency(
        conformal_result=conformal_result,
        vehicle=vehicle,
        symptom=guard.text,
        vision_observations=observations,
    )
    if not sufficiency.sufficient:
        follow_ups: tuple[str, ...]
        if rule and rule.get("follow_up"):
            follow_ups = (str(rule["follow_up"]),)
        elif "wide_or_empty_conformal_prediction_set" in sufficiency.missing:
            follow_ups = (
                "Which warning light or symptom is showing, and when did it start?",
                "What is the vehicle make, model and year?",
            )
        else:
            follow_ups = (
                "Please share the vehicle make, model and year.",
                "What exactly happens — sound, warning light, or smell — and when?",
            )
        return RouteDecision(
            Route.HITL,
            "insufficient_or_uncertain_context:" + ",".join(sufficiency.missing),
            follow_ups=follow_ups,
            max_tokens=0,
            estimated_context_tokens=0,
        )

    if rule:
        template = ""
        if isinstance(rule.get("diagnosis"), dict):
            template = str(rule["diagnosis"].get("summary") or "")
        return RouteDecision(
            Route.TEMPLATE,
            "deterministic_rule_match",
            template=template,
            max_tokens=0,
            estimated_context_tokens=0,
        )

    return RouteDecision(
        Route.LLM,
        "complex_multi_symptom_synthesis",
        max_tokens=max_tokens,
        estimated_context_tokens=context.estimated_tokens,
    )
