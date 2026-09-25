"""REST views: chat, upload, diagnosis, booking, history, health."""
import logging
import time
import uuid
from collections import defaultdict

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Booking, ChatMessage, ChatSession, Diagnosis, MediaUpload
from .serializers import (
    BookingSerializer,
    ChatMessageSerializer,
    DiagnosisSerializer,
    MediaUploadSerializer,
)
from .services import ai_service
from .services.media import safe_filename, validate_upload
from .services.triage import (
    SHORT_GENERIC,
    build_follow_up,
    extract_vehicle_details,
    find_rule,
    is_greeting,
    is_unsafe,
    looks_car_related,
)

logger = logging.getLogger(__name__)

# Simple in-memory per-session rate limiting (per process; sufficient for assignment).
_RATE = defaultdict(list)


def _rate_limited(key: str) -> bool:
    now = time.time()
    window = [t for t in _RATE[key] if now - t < 60]
    _RATE[key] = window
    limit = getattr(settings, "CHAT_RATELIMIT_PER_MIN", 30)
    if len(window) >= limit:
        return True
    window.append(now)
    _RATE[key] = window
    return False


def _get_session(session_id):
    if not session_id:
        return None
    try:
        uid = uuid.UUID(str(session_id))
    except (ValueError, AttributeError):
        return None
    try:
        return ChatSession.objects.get(id=uid)
    except ChatSession.DoesNotExist:
        return None


def _history_text(session, limit=12):
    msgs = session.messages.order_by("-created_at")[:limit]
    msgs = list(reversed(msgs))
    return "\n".join(f"{m.role}: {m.content[:600]}" for m in msgs)


@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok", "service": "instant-mechanic-backend"}, status=200)


@api_view(["GET"])
def conversation_history(request, session_id):
    session = _get_session(session_id)
    if session is None:
        return Response({"error": "Unknown session id."}, status=404)
    msgs = session.messages.order_by("created_at")
    diags = session.diagnoses.order_by("-created_at")
    uploads = session.uploads.order_by("created_at")
    return Response(
        {
            "session_id": str(session.id),
            "vehicle": {
                "make": session.vehicle_make,
                "model": session.vehicle_model,
                "year": session.vehicle_year,
                "fuel": session.vehicle_fuel,
            },
            "messages": ChatMessageSerializer(msgs, many=True).data,
            "diagnoses": DiagnosisSerializer(diags, many=True).data,
            "uploads": MediaUploadSerializer(uploads, many=True).data,
        },
        status=200,
    )


@api_view(["POST"])
def chat_view(request):
    data = request.data or {}
    # Spam/bot honeypot: real clients never send `website`.
    if data.get("website"):
        return Response({"error": "Request rejected."}, status=400)
    message = str(data.get("message", "") or "")
    session_id = data.get("session_id")
    if _rate_limited(str(session_id or request.META.get("REMOTE_ADDR", "anon"))):
        return Response({"error": "Too many requests. Please wait a minute."}, status=429)

    session = _get_session(session_id)
    if session is None:
        session = ChatSession.objects.create()
    # Optional vehicle payload.
    for field in ("vehicle_make", "vehicle_model", "vehicle_year", "vehicle_fuel"):
        if data.get(field):
            setattr(session, field, str(data[field])[:80])
    # Best-effort extraction from free text.
    extracted = extract_vehicle_details(message)
    for k, v in extracted.items():
        if v and not getattr(session, k, ""):
            setattr(session, k, v[:80])
    session.save()

    if len(message) > 2000:
        return Response({"error": "Message too long (max 2000 characters)."}, status=400)

    history_count = session.messages.count()
    decision = build_follow_up(session, message, history_count)

    # Persist user message (even greetings/rejections, for history) unless empty.
    if message.strip():
        ChatMessage.objects.create(session=session, role="user", content=message.strip(), ai_used=False)
    else:
        return Response(
            {"session_id": str(session.id), "reply": decision["reply"], "action": "follow_up",
             "needs_info": decision.get("needs_info", []), "ai_used": False},
            status=200,
        )

    action = decision["action"]
    needs_info = decision.get("needs_info", [])

    # Deterministic follow-ups / rejections / greetings: no AI call.
    if action in ("follow_up", "reject", "greet"):
        # For car-related vague input with history, optionally enrich with Groq
        # only when it materially improves (nuanced symptoms, no rule matched).
        reply = decision["reply"]
        ai_used = False
        use_ai = (
            action == "follow_up"
            and ai_service.is_configured()
            and looks_car_related(message)
            and find_rule(message) is None
            and len(message.split()) >= 3  # lowered from 6 → 3 for richer AI follow-ups
            and history_count >= 0          # fire on first message too
        )
        if use_ai:
            try:
                hist = _history_text(session, limit=8)
                ai_reply = ai_service.groq_chat(
                    [{"role": "user", "content": f"History:\n{hist}\n\nLatest user message: {message}\nAsk ONE short follow-up question as a senior mechanic."}],
                    max_tokens=200,
                )
                if ai_reply:
                    reply = ai_reply
                    ai_used = True
            except ai_service.AIServiceError:
                pass  # deterministic fallback reply stands
            except Exception:
                logger.warning("Groq chat fallback", exc_info=False)
                pass
        ChatMessage.objects.create(session=session, role="assistant", content=reply, ai_used=ai_used)
        code = 200
        if action == "reject":
            code = 200  # valid request, polite rejection (not a 4xx)
        return Response(
            {"session_id": str(session.id), "reply": reply, "action": action,
             "needs_info": needs_info, "ai_used": ai_used,
             "unsafe": is_unsafe(message)},
            status=code,
        )

    # action == ready: tell client diagnosis can be requested; also provide quick guidance.
    reply = decision["reply"]
    if is_unsafe(message):
        reply += " If you see smoke/fire or smell fuel, stop safely, switch off, and call +91 9266961110 now."
    ChatMessage.objects.create(session=session, role="assistant", content=reply, ai_used=False)
    return Response(
        {"session_id": str(session.id), "reply": reply, "action": "ready",
         "needs_info": [], "ai_used": False, "diagnosis_ready": True,
         "unsafe": is_unsafe(message)},
        status=200,
    )


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_view(request):
    session_id = request.data.get("session_id")
    session = _get_session(session_id)
    if session is None:
        return Response({"error": "Valid session_id is required."}, status=400)
    f = request.FILES.get("file")
    if f is None:
        return Response({"error": "No file provided. Use multipart field 'file'."}, status=400)
    try:
        kind, _ = validate_upload(f)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    # Safe storage name; keep original name in DB only.
    original_name = str(f.name)[:255]
    f.name = safe_filename(original_name)
    upload = MediaUpload.objects.create(
        session=session,
        file=f,
        original_name=original_name,
        mime_type=getattr(f, "content_type", "")[:120],
        size_bytes=f.size,
        kind=kind,
    )
    # Media analysis: only images get lightweight note; audio/video are stored, not AI-analyzed
    # (Groq text model cannot analyze binary media). Never fabricate observations.
    if kind == "image":
        try:
            from PIL import Image
            with Image.open(upload.file.path) as im:
                w, h = im.size
            upload.analyzed = False
            upload.analysis_note = (
                f"Image received ({w}x{h}, {upload.size_bytes/1024:.0f} KB). "
                "Visual content was not auto-analyzed; a mechanic will review it during inspection."
            )
            upload.save()
        except Exception:
            upload.analysis_note = "Image received but could not be previewed. A mechanic will review it."
            upload.save()
    else:
        upload.analysis_note = (
            f"{kind.title()} file received ({upload.size_bytes/1048576:.1f} MB). "
            "Audio/video contents are stored for the mechanic and were not auto-transcribed by AI."
        )
        upload.save()
    ChatMessage.objects.create(
        session=session, role="user",
        content=f"[Uploaded {kind}: {upload.original_name}]",
        ai_used=False,
    )
    return Response(
        {"id": str(upload.id), "session_id": str(session.id), "kind": kind,
         "size_bytes": upload.size_bytes, "analyzed": upload.analyzed,
         "note": upload.analysis_note},
        status=201,
    )


def _rule_diagnosis(session, text: str):
    rule = find_rule(text)
    if not rule:
        return None
    d = dict(rule["diagnosis"])
    d["supporting_symptoms"] = [text[:300]]
    return d, False


@api_view(["POST"])
def diagnosis_view(request):
    data = request.data or {}
    if data.get("website"):
        return Response({"error": "Request rejected."}, status=400)
    session = _get_session(data.get("session_id"))
    if session is None:
        return Response({"error": "Valid session_id is required."}, status=400)
    if _rate_limited("diag-" + str(session.id)):
        return Response({"error": "Too many requests. Please wait a minute."}, status=429)

    history = _history_text(session, limit=15)
    user_msgs = session.messages.filter(role="user").count()
    if user_msgs == 0:
        return Response(
            {"error": "Not enough information. Describe your car problem first (symptoms, sounds, warning lights)."},
            status=400,
        )
    # Insufficient info: only greeting/smalltalk so far (greetings don't count).
    def _substantive(text: str) -> bool:
        t = (text or "").strip()
        if t.startswith("[Uploaded"):
            return True  # media counts as substantive context
        if is_greeting(t) or SHORT_GENERIC.match(t):
            return False
        return looks_car_related(t)

    car_related_any = any(
        _substantive(m.content)
        for m in session.messages.filter(role="user")
    )
    if not car_related_any:
        return Response(
            {"error": "Not enough car-related detail yet. Please describe the vehicle and symptoms before diagnosis."},
            status=422,
        )

    vehicle = " ".join(x for x in [session.vehicle_make, session.vehicle_model, session.vehicle_year, session.vehicle_fuel] if x)
    # 1) Deterministic rules first (no AI).
    rule_result = _rule_diagnosis(session, history)
    payload = None
    ai_used = False
    if rule_result:
        payload, ai_used = rule_result
    elif ai_service.is_configured():
        # 2) Groq for nuanced cases only.
        try:
            payload = ai_service.groq_structured_diagnosis(history, vehicle)
            ai_used = True
        except ai_service.AIServiceError as e:
            if e.kind == "missing_key":
                pass  # fall through to generic deterministic diagnosis
            elif e.kind in ("rate_limit", "timeout"):
                return Response({"error": str(e)}, status=503 if e.kind == "rate_limit" else 504)
            else:
                # Provider/invalid response: fall back to safe generic diagnosis rather than failing.
                logger.warning("Groq diagnosis fallback: %s", e.kind)
                pass
        except Exception:
            # Never leak provider internals; fall back safely.
            logger.warning("Groq diagnosis unexpected error; using fallback", exc_info=False)
            pass
    if payload is None:
        # Safe generic deterministic fallback (always available, no AI needed).
        payload = {
            "summary": "Preliminary assessment based on your description. An in-person inspection is recommended to confirm.",
            "possible_causes": ["Issue requires physical inspection to narrow down"],
            "supporting_symptoms": [history[:300]],
            "recommended_service": "general_repair",
            "next_steps": [
                "Note when the symptom occurs (start, idle, driving, braking)",
                "Check dashboard warning lights and fluid levels if safe",
                "Book a mechanic inspection or call +91 9266961110 for roadside help",
            ],
            "urgency": "medium",
            "drive_guidance": "If any red warning light, smoke, or unusual handling appears, stop safely and do not continue driving.",
            "safety_warning": "This is a preliminary remote assessment, not a confirmed mechanical inspection.",
            "inspection_recommended": True,
        }
        ai_used = False

    # Conservative safety override.
    if is_unsafe(history):
        payload["urgency"] = "critical"
        payload["drive_guidance"] = "DO NOT DRIVE. Stop in a safe location, switch off the engine, and call +91 9266961110."
        if not payload.get("safety_warning"):
            payload["safety_warning"] = "Potential safety-critical fault. Keep clear and seek qualified help."

    diag = Diagnosis.objects.create(
        session=session,
        summary=payload["summary"][:1000],
        possible_causes=payload.get("possible_causes", [])[:8],
        supporting_symptoms=payload.get("supporting_symptoms", [])[:8],
        recommended_service=payload.get("recommended_service", "general_repair"),
        next_steps=payload.get("next_steps", [])[:8],
        urgency=payload.get("urgency", "medium"),
        drive_guidance=str(payload.get("drive_guidance", ""))[:1000],
        safety_warning=str(payload.get("safety_warning", ""))[:1000],
        inspection_recommended=bool(payload.get("inspection_recommended", True)),
        ai_generated=ai_used,
    )
    disclaimer = "Preliminary remote assessment — not a confirmed mechanical inspection. In-person check recommended."
    ChatMessage.objects.create(
        session=session, role="assistant",
        content=f"Diagnosis ready: {diag.summary} [{disclaimer}]",
        ai_used=ai_used,
    )
    data_out = DiagnosisSerializer(diag).data
    data_out["disclaimer"] = disclaimer
    data_out["ai_used"] = ai_used
    return Response(data_out, status=201)


@api_view(["POST"])
def booking_view(request):
    data = request.data or {}
    if data.get("website"):
        return Response({"error": "Request rejected."}, status=400)
    mutable = dict(data)
    # Resolve session/diag UUIDs.
    sess = _get_session(data.get("session_id"))
    if data.get("session_id") and sess is None:
        return Response({"session_id": "Unknown session id."}, status=400)
    if sess:
        mutable["session"] = str(sess.id)
    diag = None
    if data.get("diagnosis_id"):
        try:
            diag = Diagnosis.objects.get(id=uuid.UUID(str(data["diagnosis_id"])))
        except (ValueError, Diagnosis.DoesNotExist):
            return Response({"diagnosis_id": "Unknown diagnosis id."}, status=400)
        mutable["diagnosis"] = str(diag.id)
        if sess and diag.session_id != sess.id:
            return Response({"diagnosis": "Diagnosis does not belong to this chat session."}, status=400)
        if not sess:
            mutable["session"] = str(diag.session_id)
    ser = BookingSerializer(data=mutable)
    if not ser.is_valid():
        return Response(ser.errors, status=400)
    booking = ser.save(status="pending")
    out = BookingSerializer(booking).data
    out["message"] = "Booking received. Our team will call to confirm. For urgent help call +91 9266961110."
    return Response(out, status=201)


@api_view(["GET"])
def booking_detail(request, id):
    try:
        uid = uuid.UUID(str(id))
    except (ValueError, AttributeError):
        return Response({"error": "Invalid booking id."}, status=404)
    booking = get_object_or_404(Booking, id=uid)
    # Session isolation: if session_id query given, it must match.
    q = request.query_params.get("session_id")
    if q:
        s = _get_session(q)
        if s is None or (booking.session_id and booking.session_id != s.id):
            return Response({"error": "Booking not found for this session."}, status=404)
    data = BookingSerializer(booking).data
    # Attach related diagnosis summary for convenience.
    if booking.diagnosis_id:
        try:
            d = Diagnosis.objects.get(id=booking.diagnosis_id)
            data["diagnosis"] = DiagnosisSerializer(d).data
        except Diagnosis.DoesNotExist:
            pass
    return Response(data, status=200)
