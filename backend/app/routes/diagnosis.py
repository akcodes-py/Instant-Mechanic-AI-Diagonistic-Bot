"""POST /api/diagnosis/ — rules first, Groq only when needed, safe fallback."""
import logging

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SERVICE_TYPES, URGENCY_LEVELS
from app.database import get_db
from app.models import ChatMessage, Diagnosis
from app.routes.common import error_response
from app.schemas import DiagnosisRequest, diagnosis_out
from app.services import ai_service
from app.services.session_store import (
    get_session,
    history_text,
    rate_limited,
    user_message_count,
    user_messages,
)
from app.services.triage import (
    SHORT_GENERIC,
    find_rule,
    is_greeting,
    is_unsafe,
    looks_car_related,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _substantive(text: str) -> bool:
    value = (text or "").strip()
    if value.startswith("[Uploaded"):
        return True  # media counts as substantive context
    if is_greeting(value) or SHORT_GENERIC.match(value):
        return False
    return looks_car_related(value)


@router.post("/diagnosis/")
async def diagnosis(
    payload: DiagnosisRequest,
    db: AsyncSession = Depends(get_db),
):
    if payload.website:
        return error_response(400, "Request rejected.")

    session = await get_session(db, payload.session_id)
    if session is None:
        return error_response(400, "Valid session_id is required.")
    if rate_limited("diag-" + str(session.id)):
        return error_response(429, "Too many requests. Please wait a minute.")

    history = await history_text(db, session, limit=15)
    user_msgs = await user_message_count(db, session)
    if user_msgs == 0:
        return error_response(
            400,
            "Not enough information. Describe your car problem first "
            "(symptoms, sounds, warning lights).",
        )

    if not any(_substantive(message.content) for message in await user_messages(db, session)):
        return error_response(
            422,
            "Not enough car-related detail yet. Please describe the vehicle and "
            "symptoms before diagnosis.",
        )

    vehicle = " ".join(
        value
        for value in (
            session.vehicle_make,
            session.vehicle_model,
            session.vehicle_year,
            session.vehicle_fuel,
        )
        if value
    )

    diagnosis_payload = None
    ai_used = False

    # 1) Deterministic rules first (no AI).
    rule = find_rule(history)
    if rule:
        diagnosis_payload = dict(rule["diagnosis"])
        diagnosis_payload["supporting_symptoms"] = [history[:300]]
    elif ai_service.is_configured():
        # 2) Groq for nuanced cases only.
        try:
            diagnosis_payload = await run_in_threadpool(
                ai_service.groq_structured_diagnosis,
                history,
                vehicle,
            )
            ai_used = True
        except ai_service.AIServiceError as exc:
            if exc.kind == "missing_key":
                pass  # fall through to generic deterministic diagnosis
            elif exc.kind in ("rate_limit", "timeout"):
                return error_response(503 if exc.kind == "rate_limit" else 504, str(exc))
            else:
                # Provider/invalid response: fall back to safe generic diagnosis.
                logger.warning("Groq diagnosis fallback: %s", exc.kind)
        except Exception:
            # Never leak provider internals; fall back safely.
            logger.warning("Groq diagnosis unexpected error; using fallback", exc_info=False)

    if diagnosis_payload is None:
        # Safe generic deterministic fallback (always available, no AI).
        diagnosis_payload = {
            "summary": (
                "Preliminary assessment based on your description. An in-person "
                "inspection is recommended to confirm."
            ),
            "possible_causes": ["Issue requires physical inspection to narrow down"],
            "supporting_symptoms": [history[:300]],
            "recommended_service": "general_repair",
            "next_steps": [
                "Note when the symptom occurs (start, idle, driving, braking)",
                "Check dashboard warning lights and fluid levels if safe",
                "Book a mechanic inspection or call +91 9266961110 for roadside help",
            ],
            "urgency": "medium",
            "drive_guidance": (
                "If any red warning light, smoke, or unusual handling appears, stop "
                "safely and do not continue driving."
            ),
            "safety_warning": (
                "This is a preliminary remote assessment, not a confirmed "
                "mechanical inspection."
            ),
            "inspection_recommended": True,
        }
        ai_used = False

    # Conservative safety override.
    if is_unsafe(history):
        diagnosis_payload["urgency"] = "critical"
        diagnosis_payload["drive_guidance"] = (
            "DO NOT DRIVE. Stop in a safe location, switch off the engine, and "
            "call +91 9266961110."
        )
        if not diagnosis_payload.get("safety_warning"):
            diagnosis_payload["safety_warning"] = (
                "Potential safety-critical fault. Keep clear and seek qualified help."
            )

    recommended_service = diagnosis_payload.get("recommended_service", "general_repair")
    if recommended_service not in SERVICE_TYPES:
        recommended_service = "general_repair"
    urgency = diagnosis_payload.get("urgency", "medium")
    if urgency not in URGENCY_LEVELS:
        urgency = "medium"

    diagnosis_row = Diagnosis(
        session_id=session.id,
        summary=str(diagnosis_payload["summary"])[:1000],
        possible_causes=[
            str(item)[:300] for item in diagnosis_payload.get("possible_causes", [])
        ][:8],
        supporting_symptoms=[
            str(item)[:300] for item in diagnosis_payload.get("supporting_symptoms", [])
        ][:8],
        recommended_service=recommended_service,
        next_steps=[
            str(item)[:300] for item in diagnosis_payload.get("next_steps", [])
        ][:8],
        urgency=urgency,
        drive_guidance=str(diagnosis_payload.get("drive_guidance", ""))[:1000],
        safety_warning=str(diagnosis_payload.get("safety_warning", ""))[:1000],
        inspection_recommended=bool(diagnosis_payload.get("inspection_recommended", True)),
        ai_generated=ai_used,
    )
    db.add(diagnosis_row)
    await db.commit()
    await db.refresh(diagnosis_row)

    disclaimer = (
        "Preliminary remote assessment — not a confirmed mechanical inspection. "
        "In-person check recommended."
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=f"Diagnosis ready: {diagnosis_row.summary} [{disclaimer}]",
            ai_used=ai_used,
        )
    )
    await db.commit()

    output = diagnosis_out(diagnosis_row)
    output["disclaimer"] = disclaimer
    output["ai_used"] = ai_used
    return JSONResponse(status_code=201, content=output)
