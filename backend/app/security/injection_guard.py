"""Two-layer prompt-injection defense ported from ShopAssist.

Layer 1 mirrors ``shared/prompting.scrub``: cheap normalization rules that
remove known cost-bait ("step by step", "quote the policy", ...). Layer 2 is a
deterministic heuristic classifier that fails closed on role overrides,
off-topic hijacks, prompt/rule extraction and delimiter smuggling. The
multi-turn sanitizer applies BOTH layers to every message before history is
reconstructed, so an instruction planted in turn 1 cannot fire in turn 3.

No model, network or API key is involved. Keeping the layers deterministic is
what makes the behavior testable and reproducible on a local machine.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

# ---- Layer 1: known cost / verbosity bait (direct ShopAssist port) --------

_VERBOSE_RE = re.compile(
    r"step[\s-]*by[\s-]*step|full\s+reasoning|detailed\s+plan|double[\s-]*check|"
    r"restate\s+the\s+ticket|quote\s+the|list\s+each\s+step|verbatim|"
    r"write\s+a\s+detailed|reproduce\s+the",
    re.IGNORECASE,
)

# ---- Layer 2: heuristic semantic check ----------------------------------

# A hit on any hard pattern blocks the message outright. These are phrased
# narrowly so ordinary Hinglish/English symptom descriptions stay unaffected.
_HARD_RE = re.compile(
    r"ignore\s+(all\s+|the\s+)?(previous|prior|above|earlier|system)\s+(instruction|message|prompt|rule)|"
    r"disregard\s+(all\s+|the\s+)?(previous|prior|above|earlier)|"
    r"quote\s+the\s+(system|policy|prompt|rules)|"
    r"system\s*:|assistant\s*:|developer\s*:|"
    r"you\s+are\s+now|act\s+as\s+(if|a|an|the)|new\s+instructions|override\s+instructions|"
    r"reveal\s+your\s+(system|prompt|instructions|rules)|"
    r"print\s+your\s+(system|prompt|instructions|rules)|"
    r"show\s+your\s+(system|prompt|hidden|internal)|"
    r"(chain[\s-]*of[\s-]*thought|show\s+(me\s+)?your\s+reasoning)|"
    r"forget\s+(the\s+)?car|stop\s+talking\s+about\s+(cars?|vehicles?)|"
    r"[<\[]\s*\|?\s*(system|im_start|inst)\s*[>\]]|"
    r"```\s*(system|prompt)|"
    r"\b(bypass|disable|disconnect|reset)\b[^.!\n]{0,60}\b(sensor|airbag|abs|brake|warning\s+light|fault\s+code)|"
    r"decode\s+this|follow\s+the\s+embedded",
    re.IGNORECASE,
)

# Softer signals: two or more together are enough to fail closed.
_SOFT_PATTERNS = (
    re.compile(r"\b(prompt|instructions?|rules?|policy|policies)\b", re.IGNORECASE),
    re.compile(r"\b(internal|hidden|secret|confidential)\b", re.IGNORECASE),
    re.compile(r"\b(bypass|disable|turn\s+off|override)\b", re.IGNORECASE),
    re.compile(r"\b(base64|hex\s+decode|decode\s+this|zero[\s-]*width|unicode\s+escape)\b", re.IGNORECASE),
    re.compile(r"&#x?[0-9a-f]+;|\\u[0-9a-f]{4}|\\x[0-9a-f]{2}", re.IGNORECASE),
)

_MAX_MESSAGE_CHARS = 2000


@dataclass(frozen=True)
class GuardResult:
    """Outcome of one message check."""

    text: str
    blocked: bool
    reasons: tuple[str, ...] = ()


def normalize(text: str) -> str:
    """NFKC-normalize, collapse whitespace and strip zero-width smuggling."""
    value = unicodedata.normalize("NFKC", text or "")
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", value)
    return " ".join(value.split())


def scrub(text: str) -> str:
    """Layer 1: remove customer instructions that trigger verbose output."""
    return _VERBOSE_RE.sub("", text or "")


def assess(text: str) -> GuardResult:
    """Layer 2: deterministic heuristic classifier. Fail closed on a hard hit."""
    value = normalize(text)
    reasons: list[str] = []
    hard = _HARD_RE.search(value)
    if hard:
        reasons.append("role_override_or_extraction")
    soft_hits = sum(1 for pattern in _SOFT_PATTERNS if pattern.search(value))
    if soft_hits >= 2:
        reasons.append("combined_suspicious_signals")
    if len(value) > _MAX_MESSAGE_CHARS:
        reasons.append("oversized_input")
    return GuardResult(value, bool(reasons), tuple(reasons))


def sanitize_message(text: str, max_chars: int = _MAX_MESSAGE_CHARS) -> GuardResult:
    """Run both layers on a single incoming message.

    Blocked messages return an empty string so no part of them can reach the
    provider. This is the stricter-than-a-phrase-list behavior ported from
    ShopAssist's ``safe_thread``.
    """
    original = normalize(text or "")[:max_chars]
    # Check the raw text first: Layer 1 removes "quote the ..." bait, which
    # would otherwise hide an extraction attempt from Layer 2.
    first = assess(original)
    if first.blocked:
        return GuardResult("", True, first.reasons)
    layer1 = scrub(original)
    result = assess(layer1)
    if result.blocked:
        return GuardResult("", True, result.reasons)
    return GuardResult(normalize(layer1), False, ())


def sanitize_thread(messages: Iterable[dict]) -> list[dict]:
    """Clean every prior turn before the history is rebuilt for the LLM.

    A blocked turn is dropped entirely: a payload in turn 1 therefore cannot
    survive into turn 3. Roles are restricted to the two allowed values.
    """
    clean: list[dict] = []
    for message in messages or ():
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        result = sanitize_message(str(message.get("content") or ""))
        if result.blocked or not result.text:
            continue
        clean.append({"role": role, "content": result.text})
    return clean


def injection_blocked(text: str) -> bool:
    """Convenience predicate used by the router and tests."""
    return sanitize_message(text).blocked
