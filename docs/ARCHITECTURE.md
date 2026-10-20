# Architecture

```
Browser (React+Vite+TS+Tailwind, S3 + CloudFront)
  │  fetch (VITE_API_URL only, no secrets)
  ▼
FastAPI + Uvicorn (AWS EC2, async SQLAlchemy + aiosqlite, media at MEDIA_ROOT)
  ├─ app/main.py           — app, CORS, lifespan (create tables + media dir), router mounts
  ├─ app/routes/           — health, chat, upload, diagnosis, booking, history
  ├─ app/schemas.py        — Pydantic request models + JSON serializers
  ├─ app/models.py         — SQLAlchemy models (same 5 tables)
  ├─ app/database.py       — async engine, session factory, init_db
  ├─ app/services/
  │   ├─ triage.py         — deterministic: relevance gate, follow-ups, 7 symptom rules, safety override
  │   ├─ ai_service.py     — ONLY Groq calls (chat + structured diagnosis), error mapping, JSON validation
  │   ├─ media.py          — extension + magic-byte checks, size limits, safe filenames
  │   └─ session_store.py  — session lookup, history text, message counts, in-memory rate limiting
  └─ app/config.py         — pydantic-settings, env-driven, CORS allowlist
```

## Database
- `chat_sessions` (UUID, vehicle_* fields, timestamps)
- `chat_messages` (session FK, role user/assistant/system, content, ai_used, index on session+created_at)
- `media_uploads` (session FK, file path outside executable paths, original_name, mime, size, kind, analyzed=false + honest note)
- `diagnoses` (session FK, summary, JSON lists, recommended_service, urgency, drive/safety text, inspection_recommended, ai_generated, index on session+created_at)
- `bookings` (session FK nullable SET NULL, diagnosis FK nullable SET NULL, name/phone/service/location..., status pending default, indexes on created_at/phone)
- Anonymous UUID sessions (no auth per assignment scope); session isolation enforced on booking/diagnosis/history reads.

## AI minimization
1. Reject/greet/follow-up deterministically (zero AI) for empty, greeting, irrelevant, and rule-matched inputs.
2. Groq chat used only for vague-but-car-related multi-word inputs with history (single follow-up question).
3. Diagnosis: rule match → no AI; else Groq structured JSON (validated, normalized) → else safe generic fallback. Booking never needs AI.
