"""POST /api/chat/ — deterministic first, optional Groq follow-up."""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ChatMessage, ChatSession
from app.routes.common import error_response
from app.schemas import ChatRequest
from app.security.middleware import api_rate_limit, limiter
from app.security.audit_logger import client_ip_from_request, log_security_event
from app.security.injection_guard import injection_blocked
from app.security.policy_router import Route, build_bounded_context, route as decide_route
from app.services import ai_service
from app.services.session_store import (
    get_session,
    history_messages,
    message_count,
    rate_limited,
)
from app.services.triage import (
    build_follow_up,
    extract_vehicle_details,
    find_rule,
    is_unsafe,
    looks_car_related,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat/")
@limiter.limit(api_rate_limit)
async def chat(
    payload: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if payload.website:
        return error_response(400, "Request rejected.")

    message = payload.message or ""
    rate_key = str(payload.session_id or (request.client.host if request.client else "anon"))
    if rate_limited(rate_key):
        return error_response(429, "Too many requests. Please wait a minute.")

    # Prompt-injection attempts are logged for VAPT evidence. The deterministic
    # reply still runs; the guard simply prevents the payload reaching Groq.
    if injection_blocked(message):
        log_security_event(
            "PROMPT_INJECTION_BLOCKED",
            client_ip=client_ip_from_request(request),
            endpoint="/api/chat/",
            status=200,
            detail="injection_guard_layer2",
        )

    session = await get_session(db, payload.session_id)
    if session is None:
        session = ChatSession()
        db.add(session)

    # Optional vehicle payload.
    for field in ("vehicle_make", "vehicle_model", "vehicle_year", "vehicle_fuel"):
        value = getattr(payload, field)
        if value:
            setattr(session, field, str(value)[:80])

    # Best-effort extraction from free text.
    extracted = extract_vehicle_details(message)
    for key, value in extracted.items():
        if value and not getattr(session, key, ""):
            setattr(session, key, value[:80])

    await db.commit()
    await db.refresh(session)

    if len(message) > 2000:
        return error_response(400, "Message too long (max 2000 characters).")

    history_count = await message_count(db, session)
    decision = build_follow_up(session, message, history_count)

    if not message.strip():
        return {
            "session_id": str(session.id),
            "reply": decision["reply"],
            "action": "follow_up",
            "needs_info": decision.get("needs_info", []),
            "ai_used": False,
        }

    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=message.strip(),
            ai_used=False,
        )
    )
    await db.commit()

    action = decision["action"]
    needs_info = decision.get("needs_info", [])

    # Deterministic follow-ups / rejections / greetings: no AI call.
    if action in ("follow_up", "reject", "greet"):
        reply = decision["reply"]
        ai_used = False
        use_ai = (
            action == "follow_up"
            and ai_service.is_configured()
            and looks_car_related(message)
            and find_rule(message) is None
            and len(message.split()) >= 3
            and history_count >= 0
        )
        if use_ai:
            try:
                # Ported ShopAssist gate: sanitize every turn, bound the window,
                # and only spend tokens when the router sees genuine ambiguity.
                prior = await history_messages(db, session, limit=8)
                routing = decide_route(
                    message,
                    history=prior,
                    vehicle={
                        "make": session.vehicle_make,
                        "model": session.vehicle_model,
                        "year": session.vehicle_year,
                        "fuel": session.vehicle_fuel,
                    },
                )
                use_ai = routing.route is Route.LLM
                if use_ai:
                    bounded = build_bounded_context(prior, message)
                    prompt = (
                        f"History (sanitized, bounded):\n{bounded.text}\n"
                        "Ask ONE short follow-up question as a senior mechanic."
                    )
                    ai_reply = await run_in_threadpool(
                        ai_service.groq_chat,
                        [{"role": "user", "content": prompt}],
                        max_tokens=min(200, routing.max_tokens),
                    )
                else:
                    ai_reply = ""
                if ai_reply:
                    reply = ai_reply
                    ai_used = True
            except ai_service.AIServiceError:
                pass  # deterministic fallback reply stands
            except Exception:
                logger.warning("Groq chat fallback", exc_info=False)

        db.add(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content=reply,
                ai_used=ai_used,
            )
        )
        await db.commit()
        return {
            "session_id": str(session.id),
            "reply": reply,
            "action": action,
            "needs_info": needs_info,
            "ai_used": ai_used,
            "unsafe": is_unsafe(message),
        }

    # action == "ready": tell the client diagnosis can be requested.
    reply = decision["reply"]
    if is_unsafe(message):
        reply += (
            " If you see smoke/fire or smell fuel, stop safely, switch off, "
            "and call +91 6392077642 now."
        )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=reply,
            ai_used=False,
        )
    )
    await db.commit()
    return {
        "session_id": str(session.id),
        "reply": reply,
        "action": "ready",
        "needs_info": [],
        "ai_used": False,
        "diagnosis_ready": True,
        "unsafe": is_unsafe(message),
    }
