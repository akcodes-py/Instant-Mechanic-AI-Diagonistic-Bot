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
  │   ├─ triage.py         — deterministic: relevance gate, follow-ups, 8 symptom rules (incl. airbag), safety override
  │   ├─ ai_service.py     — ONLY Groq calls (chat + structured diagnosis), error mapping, JSON validation
  │   ├─ media.py          — extension + magic-byte checks, size limits, safe filenames
  │   ├─ session_store.py  — session lookup, history text, message counts, in-memory rate limiting
  │   ├─ vision_service.py — optional cached Ultralytics YOLO warning-light detection (safe fallback)
  │   ├─ nlp_service.py    — optional transformer symptom classifier (lazy, safe fallback)
  │   ├─ preprocessing.py  — optional CLAHE/sharpen/contrast + blur/darkness checks
  │   ├─ calibration.py    — temperature scaling, split conformal prediction, routing
  │   └─ onnx_service.py   — optional ONNX Runtime INT8 inference + timing helper
   ├─ app/security/
   │   ├─ injection_guard.py   — ShopAssist two-layer filter + multi-turn thread sanitizer
   │   ├─ policy_router.py     — template / HITL / bounded-LLM routing + MAPIE sufficiency gate
   │   ├─ image_sanitizer.py   — magic bytes, 5 MB cap, in-memory EXIF/GPS strip, enum-only vision handoff
   │   ├─ output_safety.py     — critical hazard override, unsafe-advice and hidden-context scrub
   │   └─ middleware.py        — slowapi 429 + Retry-After, security headers, log PII scrub
  └─ app/config.py         — pydantic-settings, env-driven, CORS allowlist, ML paths/flags
```

## Database
- `chat_sessions` (UUID, vehicle_* fields, timestamps)
- `chat_messages` (session FK, role user/assistant/system, content, ai_used, index on session+created_at)
- `media_uploads` (session FK, file path outside executable paths, original_name, mime, size, kind, analyzed flag + honest note; true only when a detection was stored)
- `diagnoses` (session FK, summary, JSON lists, recommended_service, urgency, drive/safety text, inspection_recommended, ai_generated, index on session+created_at)
- `bookings` (session FK nullable SET NULL, diagnosis FK nullable SET NULL, name/phone/service/location..., status pending default, indexes on created_at/phone)
- Anonymous UUID sessions (no auth per assignment scope); session isolation enforced on booking/diagnosis/history reads.

## AI / ML minimization
1. Reject/greet/follow-up deterministically (zero AI) for empty, greeting, irrelevant, and rule-matched inputs.
2. Groq chat used only for vague-but-car-related multi-word inputs with history (single follow-up question).
3. Diagnosis: rule match → no AI; else optional local classifier when `ENABLE_ML_INFERENCE=True` → else Groq structured JSON (validated, normalized) → else safe generic fallback. Booking never needs AI.
4. ML is off by default and every model load/inference failure returns a safe empty result. Uploads are analyzed only by a real configured model; audio/video are never transcribed. Unsafe-symptom handling and relevance decisions stay deterministic.

## H3 dispatch platform (ADR-001) — additive, not a replacement

The monolith above still works unchanged. A dispatch layer was added around it:

```
React /mechanic console (h3-js)  --telemetry every 5s / offers / job status-->  Kotlin Ktor :8081
        |                                                                        |
        |  WS /api/dispatch/ws/jobs/{id}                                         |  H3 Res-8 rings
        v                                                                        v
FastAPI :8000  --diagnosis.completed(Kafka)--> Redpanda --> Ktor    Redis: locks (15s) + supply (60s)
  |  /rank/eta (sklearn/LightGBM or nearest fallback) ^            SQLite (local MS SQL stand-in)
  |  MongoDB metadata (chat/messages, uploads+detections)          Cassandra / MS SQL (opt-in profiles)
  v  S3 / MinIO media keys
Parquet archive --> spark-jobs/hex_demand.py (PySpark or pandas fallback)
```

- **Contracts first:** `contracts/` holds the Kafka JSON schemas, DB DDL, Redis key
  layout and H3 conventions. `booking_id` is the shared UUID.
- **Clean Architecture:** `dispatch-service/src/main/kotlin/.../domain` has no
  framework/DB imports; ports are `SpatialIndex`, `PresenceStore`, `OfferLockStore`,
  `BookingRepository`, `RankingStrategy`, `EventPublisher`. 16 JUnit 5 tests run in
  memory with fake ports (no Redis/Kafka/SQLite/H3 native lib).
- **Sources of truth:** Redis hot sets = offer-time presence (Cassandra = audit);
  atomic `UPDATE ... WHERE status IN ('SEARCHING','OFFERED')` = assignment; Redis
  lock = mutual exclusion only. Empty k=1→2→3 cascade emits `ESCALATED` + hotline.
- **Offline-safe:** `ENABLE_MONGO=False` and an unreachable broker leave chat →
  diagnosis → booking and all safety overrides unchanged. `/rank/eta` reports
  `model_used: false` when no model is mounted.
- **Local vs production:** Compose runs Redpanda, Redis, MongoDB and MinIO by
  default; `docker compose --profile heavy up` adds Cassandra and MS SQL.
