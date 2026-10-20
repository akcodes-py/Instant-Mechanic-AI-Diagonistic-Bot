# Instant Mechanic: DRF → FastAPI Migration Plan

> **Status (2026-10-20): implemented.** The backend is now FastAPI + async SQLAlchemy + aiosqlite under `backend/app/`, and the 37-test suite passes. This file is kept as the historical migration plan; see `README.md`, `docs/ARCHITECTURE.md`, and `AGENTS.md` for the current state.

> **Purpose:** This plan is designed to be handed to OpenCode (or any AI coding tool) step by step. Each step is self-contained with enough context to execute independently.

---

## Current State Summary

| What | Details |
|:---|:---|
| **Framework** | Django 5.1 + DRF 3.17 |
| **Database** | SQLite via Django ORM |
| **API Endpoints** | 7 endpoints under `/api/` |
| **Services** | `triage.py` (deterministic rules), `ai_service.py` (Groq), `media.py` (upload validation) |
| **Tests** | 25+ pytest tests with mocked AI |
| **Infra** | Docker, GitHub Actions CI |
| **Frontend** | React 19 + Vite + TS — calls `BASE/api/*` paths |

## Target State

| What | Details |
|:---|:---|
| **Framework** | FastAPI + Uvicorn |
| **Database** | SQLAlchemy 2.0 + aiosqlite (async SQLite) |
| **Validation** | Pydantic v2 (built into FastAPI) |
| **API Endpoints** | Same 7 paths — **zero frontend changes** |
| **Services** | Same 3 service files — minor import changes only |
| **Tests** | pytest + httpx `AsyncClient` (replaces Django test client) |
| **Infra** | Docker (uvicorn instead of gunicorn+wsgi), updated CI |

---

## New File Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              ← FastAPI app, CORS, lifespan, mount routes
│   ├── config.py             ← env settings (replaces Django settings.py)
│   ├── database.py           ← SQLAlchemy engine, async session, Base
│   ├── models.py             ← SQLAlchemy ORM models (same 5 tables)
│   ├── schemas.py            ← Pydantic request/response models (replaces serializers.py)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py         ← GET /api/health/
│   │   ├── chat.py           ← POST /api/chat/
│   │   ├── upload.py         ← POST /api/upload/
│   │   ├── diagnosis.py      ← POST /api/diagnosis/
│   │   ├── booking.py        ← POST /api/booking/ + GET /api/booking/{id}/
│   │   └── history.py        ← GET /api/history/{session_id}/
│   ├── services/
│   │   ├── __init__.py
│   │   ├── triage.py         ← COPY AS-IS (zero Django imports)
│   │   ├── ai_service.py     ← minor edit: remove `from django.conf import settings`
│   │   └── media.py          ← minor edit: remove `from django.conf import settings`
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py        ← async test fixtures (db, client)
│       ├── test_api.py        ← rewritten with httpx AsyncClient
│       └── test_ai_service.py ← mostly same, remove Django patches
├── requirements.txt           ← new dependencies
├── alembic.ini                ← DB migration config (optional)
└── alembic/                   ← migration scripts (optional)
```

---

## Step-by-Step Execution Plan

### Step 1: Backup & Prep

> **Prompt for OpenCode:**
> "Rename `backend/` to `backend_django/` to keep as reference. Create a new empty `backend/` directory with `backend/app/` and `backend/app/routes/` and `backend/app/services/` and `backend/app/tests/` subdirectories. Create empty `__init__.py` in each."

**Files created:** 5 empty `__init__.py` files

---

### Step 2: Create `requirements.txt`

> **Prompt for OpenCode:**
> "Create `backend/requirements.txt` with these exact dependencies for a FastAPI backend with async SQLite, Groq AI, image processing, and testing."

**Contents should be:**
```
fastapi==0.115.12
uvicorn[standard]==0.34.3
sqlalchemy[asyncio]==2.0.41
aiosqlite==0.21.0
pydantic==2.11.7
pydantic-settings==2.9.1
python-multipart==0.0.20
groq==1.7.0
Pillow==12.3.0
httpx==0.28.1
pytest==9.1.1
pytest-asyncio==0.26.0
pytest-cov==7.1.0
```

> [!NOTE]
> - `python-multipart` is required for FastAPI file uploads
> - `pydantic-settings` loads env variables into typed config
> - `httpx` replaces Django test client for async API testing
> - No `gunicorn`, `whitenoise`, `django-cors-headers` needed

---

### Step 3: Create `config.py` (replaces Django `settings.py`)

> **Prompt for OpenCode:**
> "Create `backend/app/config.py` using `pydantic-settings.BaseSettings` that reads all environment variables from `.env` file. Port over every setting from `backend_django/config/settings.py`."

**Must include these fields (with defaults matching current `.env.example`):**

| Field | Type | Default | Source |
|:---|:---|:---|:---|
| `DEBUG` | `bool` | `True` | `DJANGO_DEBUG` env → just `DEBUG` |
| `DATABASE_URL` | `str` | `sqlite+aiosqlite:///./db.sqlite3` | replaces `SQLITE_PATH` |
| `MEDIA_ROOT` | `str` | `./media` | same |
| `CORS_ORIGINS` | `list[str]` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | from `CORS_ALLOWED_ORIGINS` |
| `CORS_ALLOW_ALL` | `bool` | `False` | same |
| `GROQ_API_KEY` | `str` | `""` | same |
| `GROQ_MODEL` | `str` | `llama-3.3-70b-versatile` | same |
| `GROQ_TIMEOUT_S` | `float` | `20.0` | same |
| `MAX_IMAGE_MB` | `float` | `10.0` | same |
| `MAX_AUDIO_MB` | `float` | `15.0` | same |
| `MAX_VIDEO_MB` | `float` | `50.0` | same |
| `CHAT_RATELIMIT_PER_MIN` | `int` | `30` | same |

**Pattern:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... fields above ...
    class Config:
        env_file = ".env"

settings = Settings()
```

---

### Step 4: Create `database.py` (async SQLAlchemy engine)

> **Prompt for OpenCode:**
> "Create `backend/app/database.py` with async SQLAlchemy 2.0 setup: `create_async_engine`, `async_sessionmaker`, `Base = declarative_base()`. Include a `get_db` async dependency that yields sessions. Include an `init_db` coroutine that creates all tables."

**Key points:**
- Engine uses `settings.DATABASE_URL`
- `async_sessionmaker(expire_on_commit=False)`
- `get_db` is a FastAPI `Depends` that yields `AsyncSession` and auto-closes
- `init_db` calls `Base.metadata.create_all` (used in app startup lifespan)

---

### Step 5: Create `models.py` (SQLAlchemy ORM)

> **Prompt for OpenCode:**
> "Create `backend/app/models.py` converting these 5 Django models to SQLAlchemy 2.0 async models. Keep the exact same table structure, field types, constraints, defaults, and relationships. Reference: `backend_django/chatbot/models.py`."

**Conversion mapping for each model:**

| Django | SQLAlchemy |
|:---|:---|
| `UUIDField(primary_key, default=uuid4)` | `Column(String(36), primary_key=True, default=lambda: str(uuid4()))` |
| `CharField(max_length=80)` | `Column(String(80), default="")` |
| `TextField()` | `Column(Text)` |
| `JSONField(default=list)` | `Column(JSON, default=list)` |
| `BooleanField(default=False)` | `Column(Boolean, default=False)` |
| `DateTimeField(auto_now_add=True)` | `Column(DateTime, default=func.now())` |
| `ForeignKey(on_delete=CASCADE)` | `Column(String(36), ForeignKey("chatsessions.id", ondelete="CASCADE"))` |
| `ForeignKey(on_delete=SET_NULL, null=True)` | `Column(String(36), ForeignKey("...", ondelete="SET NULL"), nullable=True)` |

**5 models to convert:**
1. `ChatSession` — UUID pk, vehicle_make/model/year/fuel, timestamps
2. `ChatMessage` — UUID pk, session FK (CASCADE), role, content, ai_used, timestamp
3. `MediaUpload` — UUID pk, session FK (CASCADE), file_path, original_name, mime_type, size_bytes, kind, analyzed, analysis_note, timestamp
4. `Diagnosis` — UUID pk, session FK (CASCADE), summary, JSON fields, urgency, booleans, timestamp
5. `Booking` — UUID pk, session FK (SET_NULL nullable), diagnosis FK (SET_NULL nullable), name, phone, service_type, location, status, timestamps

> [!IMPORTANT]
> The `MediaUpload` model changes: Django's `FileField` becomes a simple `String` column storing the file path. File saving is handled manually in the route.

---

### Step 6: Create `schemas.py` (Pydantic models — replaces `serializers.py`)

> **Prompt for OpenCode:**
> "Create `backend/app/schemas.py` with Pydantic v2 models for request/response validation. Reference: `backend_django/chatbot/serializers.py`. Port all validation logic (phone regex, name length, location length, session-diagnosis ownership check)."

**Models needed:**

| Schema | Purpose | Key Validations |
|:---|:---|:---|
| `ChatRequest` | POST /api/chat/ body | `message: str`, `session_id: str | None`, `vehicle_make/model/year/fuel: str | None`, `website: str | None` (honeypot) |
| `ChatResponse` | Chat reply | `session_id, reply, action, needs_info, ai_used, unsafe, diagnosis_ready` |
| `UploadResponse` | Upload result | `id, session_id, kind, size_bytes, analyzed, note` |
| `DiagnosisRequest` | POST /api/diagnosis/ body | `session_id: str`, `website: str | None` |
| `DiagnosisResponse` | Full diagnosis | All 13 fields from Diagnosis model + `ai_used, disclaimer` |
| `BookingRequest` | POST /api/booking/ body | `name, phone, service_type, location, ...` with phone validator (`[6-9]\d{9}` Indian mobile), name ≥ 2 chars, location ≥ 5 chars, service_type must be one of 7 allowed values |
| `BookingResponse` | Booking result | All fields + `message` |
| `HistoryResponse` | Conversation history | `session_id, vehicle, messages[], diagnoses[], uploads[]` |
| `ChatMessageOut` | Message in history | `id, role, content, ai_used, created_at` |
| `MediaUploadOut` | Upload in history | `id, kind, original_name, created_at` |

---

### Step 7: Copy & Adapt Service Files

> **Prompt for OpenCode:**
> "Copy these 3 service files from `backend_django/chatbot/services/` to `backend/app/services/`. Make minimal changes — only replace Django-specific imports."

#### 7a. `triage.py` — **COPY AS-IS, ZERO CHANGES**
This file has no Django imports. It's pure Python (re, typing). Copy directly.

#### 7b. `ai_service.py` — **2 small changes:**
1. Replace `from django.conf import settings` → `from app.config import settings`
2. Change `settings.GROQ_API_KEY` → `settings.GROQ_API_KEY` (same attribute name, just different source)
3. Change `settings.GROQ_TIMEOUT_S` → `settings.GROQ_TIMEOUT_S` (same)
4. Change `settings.GROQ_MODEL` → `settings.GROQ_MODEL` (same)

That's it. All the error handling, `AIServiceError`, `parse_diagnosis_json`, `groq_chat`, `groq_structured_diagnosis` stay identical.

#### 7c. `media.py` — **2 small changes:**
1. Replace `from django.conf import settings` → `from app.config import settings`
2. All function signatures stay the same. `validate_upload` and `safe_filename` are pure Python.

> [!TIP]
> The `validate_upload` function currently accepts a Django `UploadedFile` object. In FastAPI, it receives a `UploadFile` object. The interface is similar (both have `.filename`, `.size`, `.read()`, `.seek()`), but you'll need to adapt the attribute access slightly:
> - `uploaded_file.name` → `upload_file.filename`
> - `uploaded_file.size` → `upload_file.size`
> - `uploaded_file.content_type` → `upload_file.content_type`

---

### Step 8: Create Route Files (replaces `views.py`)

Split the 433-line `views.py` into 6 focused route files. Each route file is a `APIRouter`.

> **Prompt for OpenCode:**
> "Create these 6 route files in `backend/app/routes/`. Port the logic from `backend_django/chatbot/views.py`. Use FastAPI's `APIRouter`, `Depends` for DB sessions, Pydantic schemas for validation, and async def for all endpoints. Keep the exact same API paths and response formats."

#### 8a. `routes/health.py`
- `GET /api/health/` → returns `{"status": "ok", "service": "instant-mechanic-backend"}`
- Simplest file. 5 lines.

#### 8b. `routes/chat.py` — Port `chat_view` (lines 100-194 of views.py)
- `POST /api/chat/`
- Same logic: honeypot check → rate limit → get/create session → extract vehicle details → build_follow_up → optional Groq AI enrichment → persist messages → return response
- **Rate limiting:** Keep the same in-memory `defaultdict` approach (sufficient for portfolio)
- **Key difference:** Use `async def`, `db: AsyncSession = Depends(get_db)`, and SQLAlchemy queries instead of Django ORM
- Django ORM → SQLAlchemy mapping:
  - `ChatSession.objects.create()` → `db.add(ChatSession(...))` + `await db.commit()`
  - `session.messages.count()` → `await db.scalar(select(func.count(ChatMessage.id)).where(...))`
  - `session.messages.order_by("-created_at")[:limit]` → `await db.scalars(select(ChatMessage).where(...).order_by(ChatMessage.created_at.desc()).limit(limit))`
  - `ChatMessage.objects.create(...)` → `db.add(ChatMessage(...))` + `await db.commit()`

#### 8c. `routes/upload.py` — Port `upload_view` (lines 197-254)
- `POST /api/upload/`
- Accept `UploadFile` from FastAPI (not Django's `MultiPartParser`)
- Save file manually: `settings.MEDIA_ROOT / safe_filename` → write bytes to disk
- Same PIL Image dimension check for images
- **Key difference:** FastAPI `UploadFile` instead of `request.FILES.get("file")`

#### 8d. `routes/diagnosis.py` — Port `diagnosis_view` (lines 257-376)
- `POST /api/diagnosis/`
- Same logic: validate session → check substantive messages → try rule-based → try Groq → fallback → safety override → persist Diagnosis → return
- Longest route file (~120 lines)

#### 8e. `routes/booking.py` — Port `booking_view` + `booking_detail` (lines 379-432)
- `POST /api/booking/` — create booking with Pydantic validation (phone, name, location, service_type)
- `GET /api/booking/{id}/` — retrieve booking with optional session isolation
- Pydantic handles the validation that DRF serializer did (phone regex, name length, etc.)

#### 8f. `routes/history.py` — Port `conversation_history` (lines 75-97)
- `GET /api/history/{session_id}/`
- Query session + related messages, diagnoses, uploads
- Return same JSON structure

---

### Step 9: Create `main.py` (FastAPI app entry point)

> **Prompt for OpenCode:**
> "Create `backend/app/main.py` — the FastAPI application. Include CORS middleware (using settings), lifespan event to init DB + create tables + create media directory, and mount all 6 routers."

**Structure:**
```
- Import FastAPI, CORSMiddleware
- Import settings from config
- Import init_db from database
- Import all 6 routers
- Define lifespan (async context manager): call init_db(), create MEDIA_ROOT dir
- Create FastAPI app with lifespan
- Add CORSMiddleware with settings.CORS_ORIGINS
- Include all routers with prefix="/api"
```

**CORS config must match current Django CORS setup:**
- `allow_origins = settings.CORS_ORIGINS`
- `allow_methods = ["*"]`
- `allow_headers = ["*"]`
- `allow_credentials = True`

---

### Step 10: Rewrite Tests

> **Prompt for OpenCode:**
> "Rewrite all tests from `backend_django/chatbot/tests/test_api.py` and `test_ai_service.py` using pytest-asyncio + httpx AsyncClient for FastAPI. Keep the exact same test scenarios (25+ tests), same assertions, same mock patterns. Reference the original test files."

**Key changes from Django test client → httpx:**

| Django | FastAPI/httpx |
|:---|:---|
| `client.post(path, data=json.dumps(payload), content_type="application/json")` | `await client.post(path, json=payload)` |
| `client.get(path)` | `await client.get(path)` |
| `r.json()` | `r.json()` (same) |
| `r.status_code` | `r.status_code` (same) |
| `@pytest.mark.django_db` | `@pytest.mark.asyncio` |
| `SimpleUploadedFile(...)` | `files={"file": ("name.png", bytes, "image/png")}` |
| `override_settings(MEDIA_ROOT=...)` | Monkeypatch `settings.MEDIA_ROOT` |

**`conftest.py` must include:**
- Async fixture that creates a test database (in-memory SQLite)
- Async fixture that provides `httpx.AsyncClient` with the FastAPI `app`
- Auto-cleanup that drops tables between tests

**All 25+ test cases to port:**
1. `test_health`
2. `test_valid_chat_creates_session_and_persists`
3. `test_empty_chat_input`
4. `test_malformed_chat_long_message`
5. `test_irrelevant_rejected_politely`
6. `test_greeting_flow`
7. `test_follow_up_for_battery`
8. `test_vehicle_extraction_saved`
9. `test_diagnosis_rule_based_battery`
10. `test_diagnosis_insufficient_no_messages`
11. `test_diagnosis_insufficient_irrelevant_only`
12. `test_diagnosis_unsafe_override`
13. `test_groq_structured_success_mocked`
14. `test_missing_api_key_falls_back_without_crash`
15. `test_provider_timeout_returns_504`
16. `test_provider_rate_limit_returns_503`
17. `test_groq_chat_mocked_no_live_call`
18. `test_valid_image_upload`
19. `test_unsupported_file_rejected`
20. `test_oversized_upload_rejected`
21. `test_fake_image_content_rejected`
22. `test_booking_creation_and_retrieval`
23. `test_booking_invalid_phone`
24. `test_booking_invalid_service`
25. `test_unknown_booking_404`
26. `test_session_isolation_booking_lookup`
27. `test_diagnosis_session_mismatch_rejected`
28. `test_history_returns_conversation`
29. `test_unknown_session_history_404`
30. `test_errors_do_not_leak_secrets`
31. `test_honeypot_rejected`
32. `test_ai_service_*` (5 tests — mostly unchanged)

---

### Step 11: Update `pytest.ini`

> **Prompt for OpenCode:**
> "Update `pytest.ini` in the project root. Remove Django settings, keep pythonpath and coverage."

**New content:**
```ini
[pytest]
pythonpath = backend
testpaths = backend
addopts = -ra --cov=app --cov-report=term-missing
asyncio_mode = auto
```

---

### Step 12: Update `.env.example`

> **Prompt for OpenCode:**
> "Update `.env.example` — remove Django-specific vars, add FastAPI vars. Keep all Groq and upload settings the same."

**Remove:** `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `ENFORCE_HTTPS`
**Keep:** `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_TIMEOUT_S`, `MAX_IMAGE_MB`, `MAX_AUDIO_MB`, `MAX_VIDEO_MB`
**Add:** `DEBUG=True`, `DATABASE_URL=sqlite+aiosqlite:///./db.sqlite3`, `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`

---

### Step 13: Update `Dockerfile.backend`

> **Prompt for OpenCode:**
> "Update `Dockerfile.backend` for FastAPI + Uvicorn. Same pattern: python:3.12-slim, copy requirements, install, copy code, non-root user, expose 8000, healthcheck, CMD uvicorn."

**Key changes:**
- Remove: `python manage.py migrate` (tables auto-create on startup via lifespan)
- Replace CMD: `gunicorn config.wsgi:application ...` → `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`
- Healthcheck stays the same (hits `/api/health/`)

---

### Step 14: Update `docker-compose.yml`

> **Prompt for OpenCode:**
> "Update `docker-compose.yml` — remove Django env vars, add FastAPI vars."

**Changes:**
- Remove: `DJANGO_DEBUG`, `SQLITE_PATH`
- Add: `DATABASE_URL=sqlite+aiosqlite:////data/db.sqlite3`
- Keep: `MEDIA_ROOT=/data/media`, volume mount, healthcheck

---

### Step 15: Update GitHub Actions CI

> **Prompt for OpenCode:**
> "Update `.github/workflows/ci.yml` — remove `python manage.py check`, keep pytest, update Docker build."

**Changes in backend job:**
- Remove: `python backend/manage.py check` step
- Keep: `pip install -r backend/requirements.txt`
- Keep: `python -m pytest -q`
- Keep: Docker build step

---

### Step 16: Update Docs

> **Prompt for OpenCode:**
> "Update `README.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` — replace all Django/DRF references with FastAPI/Uvicorn. Keep the same structure and information."

**README.md changes:**
- Backend quick start: `uvicorn app.main:app --reload` instead of `python manage.py runserver`
- Remove: `python manage.py migrate` (auto on startup)
- Docker CMD: uvicorn instead of gunicorn+wsgi
- Tech stack line: "Backend (FastAPI + SQLAlchemy + SQLite)" instead of "Backend (Django + DRF + SQLite)"

**ARCHITECTURE.md changes:**
- Update the ASCII diagram to show FastAPI structure
- Same service descriptions, just different file paths

---

### Step 17: Update Frontend (if needed)

**No frontend changes required** if you keep the same API paths with trailing slashes:
- `/api/health/`
- `/api/chat/`
- `/api/upload/`
- `/api/diagnosis/`
- `/api/booking/`
- `/api/booking/{id}/`
- `/api/history/{session_id}/`

> [!IMPORTANT]
> FastAPI strips trailing slashes by default. Add `redirect_slashes=True` (it's the default) or define routes WITH trailing slashes to match the frontend.

---

### Step 18: Delete Django Backup

> Only after everything works and all tests pass.
> "Delete `backend_django/` directory."

---

## Execution Order for OpenCode

Give these prompts to OpenCode **in this exact order:**

| Step | OpenCode Prompt Summary | Depends On |
|:---|:---|:---|
| 1 | Rename backend → backend_django, create new directories | — |
| 2 | Create requirements.txt | Step 1 |
| 3 | Create config.py | Step 2 |
| 4 | Create database.py | Step 3 |
| 5 | Create models.py | Step 4 |
| 6 | Create schemas.py | Step 5 |
| 7 | Copy & adapt 3 service files | Step 3 |
| 8 | Create 6 route files | Steps 5, 6, 7 |
| 9 | Create main.py | Steps 3, 4, 8 |
| 10 | Rewrite tests | Step 9 |
| 11 | Update pytest.ini | Step 10 |
| 12 | Update .env.example | Step 3 |
| 13 | Update Dockerfile.backend | Step 9 |
| 14 | Update docker-compose.yml | Step 13 |
| 15 | Update CI workflow | Step 11 |
| 16 | Update docs | Step 9 |
| 17 | Verify frontend works | Step 9 |
| 18 | Delete backend_django/ | All pass |

**Estimated total:** ~2-3 hours if done step by step with an AI coding tool.
