# AGENTS.md — Instant Mechanic

## Repo state

- AI car-mechanic chatbot plus marketing site for Delhi NCR: chat → diagnosis → booking, with roadside-help CTAs. Assignment/portfolio project, anonymous sessions (no auth).
- **Frontend:** `src/` — React 19 + Vite 8 + TypeScript 7 + Tailwind 4. State-driven SPA (`App.tsx` switches pages); no router. Typed API client in `src/api.ts`.
- **Backend:** `backend/` — FastAPI 0.139 + Uvicorn, async SQLAlchemy 2.0 + aiosqlite, SQLite, Pydantic v2. App code in `backend/app/`:
  - `main.py` — app, CORS, lifespan (tables + media dir), routers.
  - `routes/` — `health.py`, `chat.py`, `upload.py`, `diagnosis.py`, `booking.py`, `history.py`.
  - `models.py`, `schemas.py`, `database.py`, `config.py`, `constants.py`.
  - `services/` — `triage.py`, `ai_service.py`, `media.py`, `session_store.py`.
  - `tests/` — 37 pytest tests (31 API + 6 AI service).
- **Docs:** `README.md` (entry point), `docs/API.md` (endpoint contract), `docs/ARCHITECTURE.md` (layers), `docs/DEPLOYMENT.md` (AWS path), `docs/CHECKLIST.md` (manual website audit). `Full_Stack_Developer_Intern_Task (3).pdf` is the assignment brief — keep it.
- **Infra:** `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`, `.github/workflows/ci.yml`. `ec2-nginx.conf` is an untracked nginx sample for EC2.
- **Git:** `main` tracks `origin` (GitHub). Last commit 2026-09-26 (`5b16ed8`); the FastAPI migration diff is uncommitted at the time of writing. `fastapi_migration_plan.md`, `ec2-nginx.conf`, and this file are untracked.
- **The DRF → FastAPI migration is complete.** The old `backend_django/` reference tree was removed after the new suite passed; it remains in git history. `fastapi_migration_plan.md` is now a historical plan — do not re-run it or reintroduce Django/DRF.
- **No live deployment is verified.** README says "Not deployed yet"; `docs/DEPLOYMENT.md` is a guide. Never claim a URL, uptime, or smoke result that was not actually tested.
- **Measured state (2026-10-20, Python 3.14.4):** `37 passed` in ~12–19 s, total coverage **89%**; `manage.py` is gone. Frontend `npm run typecheck` and `npm run build` pass (~262 kB JS / 79 kB gzip); `npm run lint` exits 0 with two `react(set-state-in-effect)` warnings at `src/components/Site.tsx:323` and `src/components/Chatbot.tsx:45`.
- **Hygiene:** root `.coverage`, `backend/.coverage`, and old `backend/**/__pycache__` files were tracked historically. This migration removes them, and `.gitignore` now ignores Python/test artifacts. Do not re-add generated files.

## Source-of-truth rules

1. `README.md` is the entry point; `docs/API.md` is the endpoint/status-code contract; `docs/ARCHITECTURE.md` explains the layers; `backend/app/config.py` defines the real environment defaults.
2. `docs/DEPLOYMENT.md` is the current deployment target: **S3 + CloudFront for `dist/`** and **EC2 + Docker Compose + Nginx for the API**. Do not reintroduce Vercel as the deployment plan.
3. `docs/CHECKLIST.md` records a manual website audit, not automated tests. Do not cite a checked item as a test result.
4. Business figures (30,000+ cars, 4.9★, 20-minute SLA) are marketing claims marked unverified. Never present them as measured facts, and do not add new unverifiable numbers, prices, ETAs, mechanic names, or guaranteed outcomes.
5. When code and docs disagree, the running behavior plus the tests define reality; update the doc in the same change.
6. When a decision changes architecture or scope, write it down first and get user approval. `fastapi_migration_plan.md` is historical, not a standing mandate.

## Binding behavior

### Chat (`POST /api/chat/`)

- Reject honeypot payloads (`website` non-empty) with 400; cap `message` at 2000 chars; rate-limit at `CHAT_RATELIMIT_PER_MIN` (default 30/min) per session or client host; the limiter is in-memory and per process.
- Create or reuse `ChatSession`; copy vehicle fields; best-effort deterministic extraction of make/year/fuel; persist the user message before responding.
- Deterministic first (`app/services/triage.py`): greeting, empty/short generic, non-car rejection, and 7 symptom rules (battery/no-start, overheating, flat tyre, brakes, fuel, key lockout, engine noise). These paths never call Groq.
- Groq chat is only for vague-but-car-related, rule-free messages of at least 3 words when the provider is configured; a provider failure keeps the deterministic reply. Never use AI to decide relevance or safety.
- Response keys: `session_id`, `reply`, `action` (`follow_up|greet|reject|ready`), `needs_info`, `ai_used`, optionally `diagnosis_ready` and `unsafe`. Non-car queries return 200 with `action: "reject"` (not 4xx).

### Diagnosis (`POST /api/diagnosis/`)

- Requires a valid session and at least one user message (400); greetings/smalltalk only → 422.
- Rule match → no AI. Otherwise Groq structured diagnosis when configured, else the safe generic deterministic fallback. Only `rate_limit` → 503 and `timeout` → 504; other provider failures fall back without leaking details.
- Unsafe symptoms (smoke, fire, burning smell, fuel leak, brake failure, steering loss) force `urgency: critical` plus do-not-drive guidance and the emergency number.
- Persist the `Diagnosis`; return 201 with the disclaimer and an honest `ai_used` flag. The response also exposes `ai_generated` (ORM column) like the old serializer did.

### Booking (`POST /api/booking/`, `GET /api/booking/<id>/`)

- Booking never needs AI.
- Validate name ≥ 2 chars, Indian mobile (`[6-9]\d{9}`, `+91` accepted), location ≥ 5 chars, and `service_type` in the 7 allowed values. Validation failures return 400 with field-keyed messages.
- Link `session`/`diagnosis`; reject a diagnosis that belongs to another session; save as `pending`; return 201 with a confirmation message.
- Detail returns the booking (+ embedded diagnosis when linked); optional `?session_id=` enforces isolation; unknown/invalid/mismatched IDs return 404.

### Upload (`POST /api/upload/`)

- Multipart `file` plus a valid `session_id`; validate extension, magic bytes/Pillow, and size (image 10 MB, audio 15 MB, video 50 MB); store under `MEDIA_ROOT/uploads/YYYY/MM/DD/` with a UUID filename; keep the original name in the DB only.
- Images get a dimensions/received note; audio/video are stored but not transcribed. **Never claim AI understood the media.** Do not fabricate observations.
- Return 201 with `id`, `session_id`, `kind`, `size_bytes`, `analyzed: false`, and an honest note. The API does not serve stored media and there is no admin UI.

### History / health

- `GET /api/history/<session_id>/` returns `session_id`, `vehicle`, `messages[]`, `diagnoses[]`, `uploads[]`; unknown session → 404.
- `GET /api/health/` returns `{"status": "ok", "service": "instant-mechanic-backend"}`.
- All API paths end with `/`. Keep status codes and JSON field names in sync with `docs/API.md` and the interfaces in `src/api.ts`.

### Data and security invariants

- Anonymous UUID sessions: the session ID is the only capability. No auth layer exists.
- Session isolation is enforced on history, diagnosis linking, and booking lookup **when `session_id` is supplied**. `GET /api/booking/<id>/` without `session_id` returns the booking — a prototype privacy gap; do not describe it as secure.
- SQLite (`DATABASE_URL`) and local media (`MEDIA_ROOT`); Compose mounts `/data`. Single instance only: no queue, background jobs, or horizontal scaling.
- CORS uses `CORS_ORIGINS` (fallback `CORS_ALLOWED_ORIGINS`); `CORS_ALLOW_ALL` is for local debugging only.
- The app does **not** enforce HTTPS/HSTS itself. TLS is expected at CloudFront/Nginx; do not add a redirect loop behind plain HTTP.
- Uploaded files are untrusted input: keep extension/magic/size checks and UUID names. Never execute, transcribe, or “analyze” media without a real model and an evaluation.

## AI rules (Groq)

- All provider calls live in `backend/app/services/ai_service.py`. No other module imports `groq`, and the frontend never sees the key.
- `GROQ_API_KEY` is server-side only. A missing key is a normal state: deterministic paths keep working.
- Raise `AIServiceError` with a kind: `missing_key`, `timeout`, `rate_limit`, `invalid_response`, `provider_error`. Map only rate limit → 503 and timeout → 504; other provider failures fall back safely.
- Validate structured output in `parse_diagnosis_json`: required summary, enum normalization, list truncation (8 items × 300 chars), summary cap 1000. Never persist raw model text as a diagnosis.
- The system prompt stays safety-first and car-scoped: no invented prices, ETAs, names, or outcomes; recommend in-person inspection for uncertain or safety-critical cases.
- Provider calls are synchronous SDK calls run through `run_in_threadpool` from async routes. Keep them off the event loop.
- Tests mock every provider interaction. Do not add live Groq calls to tests or CI; `pytest` must not need a key.

## Frontend rules

- API base comes only from `VITE_API_URL`, default `http://127.0.0.1:8000`; never put secrets in `VITE_*` variables or source.
- `src/api.ts` is the single API surface. Keep its interfaces aligned with `docs/API.md`. It retries network/5xx twice with backoff and surfaces server messages for 4xx.
- `CONTACT` in `src/api.ts` is the canonical phone/WhatsApp/email/address source. Use it for new UI and replace hardcoded duplicates when touched.
- UX contract: mobile-first, no horizontal scroll, 44px+ targets, sticky emergency call/WhatsApp bar, accessible labels, `role="status"` for success and `role="alert"` for errors, cookie banner essential-only (no trackers).
- The chatbot must remain usable without AI (deterministic replies) and must show uploads as received-but-not-auto-analyzed.
- Keep the in-app legal pages available; they are drafts for owner review, not legal advice.

## Environment

`backend/app/config.py` uses `pydantic-settings` and reads the repo-root `.env` (plus a local `.env`). Main variables and defaults:

| Variable | Default | Notes |
|:---|:---|:---|
| `DEBUG` | `True` | `DJANGO_DEBUG` is still accepted as a legacy alias |
| `DATABASE_URL` | `sqlite+aiosqlite:///./db.sqlite3` | relative to the `backend/` working directory |
| `MEDIA_ROOT` | `./media` | Compose uses `/data/media` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | comma-separated; `CORS_ALLOWED_ORIGINS` is a fallback |
| `CORS_ALLOW_ALL` | `False` | local debugging only |
| `GROQ_API_KEY` | empty | server-side only; empty = deterministic mode |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | |
| `GROQ_TIMEOUT_S` | `20` | |
| `MAX_IMAGE_MB` / `MAX_AUDIO_MB` / `MAX_VIDEO_MB` | `10` / `15` / `50` | upload limits |
| `CHAT_RATELIMIT_PER_MIN` | `30` | in-memory limiter |
| `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `SQLITE_PATH`, `ENFORCE_HTTPS` | ignored | old Django vars; migrate local `.env` to `DATABASE_URL`/`CORS_ORIGINS` |

- `.env` is gitignored; `.env.example` is the tracked template. Never commit a real key, `db.sqlite3`, `media/`, `dist/`, `.coverage`, or `__pycache__`.
- Docker Compose loads the repo-root `.env` via `env_file` and overrides DB/media paths for `/data`.
- Tables are created by `Base.metadata.create_all` in the lifespan. **There is no Alembic setup.** `create_all` does not alter existing tables; for schema changes, add a migration framework or document a fresh-DB migration.

## Commands (real, from this machine)

Working directory: repo root (`instant-mechanic/`). No project `.venv` is present; `python` currently resolves to 3.14.4 with the backend deps installed. CI and Docker use Python 3.12; the frontend CI uses Node 20.

- Install backend deps: `python -m pip install -r backend/requirements.txt`
- Tests: `python -m pytest -q` (from root; `pytest.ini` sets `pythonpath=backend`, async mode, coverage)
- Coverage detail: `python -m pytest --cov=app --cov-report=term-missing`
- Run API: `cd backend` then `python -m uvicorn app.main:app --reload --port 8000` → `http://127.0.0.1:8000/api/health/`
- There is no `migrate` step; tables are created on startup.
- Frontend install/dev: `npm install`, `npm run dev` → `http://localhost:5173`
- Frontend gates: `npm run lint`, `npm run typecheck`, `npm run build`
- Docker: `docker compose up --build` (requires root `.env`); direct image: `docker build -f Dockerfile.backend -t instant-mechanic-backend .`
- Health check: `Invoke-RestMethod http://127.0.0.1:8000/api/health/`
- Deployment: follow `docs/DEPLOYMENT.md`; the nginx sample is `ec2-nginx.conf`.

PowerShell note: prefer script files over inline `python -c` when the snippet contains `$` or semicolons.

## Verification and gates

Fast loop for every change:

1. `python -m pytest -q` — must stay **37 passed** (31 API + 6 AI-service tests).
2. Startup smoke: `cd backend`, run Uvicorn, hit `/api/health/`, then chat → diagnosis → booking → history.
3. `npm run typecheck` and `npm run build` — clean.
4. `npm run lint` — currently 0 errors / 2 warnings; do not add warnings.
5. Manual smoke for the changed path: valid and invalid upload; 400/404/422/429/503/504; confirm errors do not leak secrets.

Current measured baseline (2026-10-20): 37 passed, 89% total coverage (`models`/`health`/`history` 100%, `schemas` 95%, `session_store` 90%, `diagnosis` 89%, `triage` 89%, `database` 88%, `upload` 87%, `booking` 84%, `chat` 83%, `main` 82%, `ai_service` 65%, `media` 63%), ~12–19 s. A TestClient smoke returned health 200, chat `greet`, booking 201; a Docker build and container smoke on the production-style `/data` paths also passed. Local Python 3.14 vs CI 3.12 is expected.

CI runs the backend install → pytest → Docker build, and frontend install → lint → typecheck → build. A deployment counts only after the live host passes `/api/health/` and the full chat/diagnosis/booking/upload flow with CORS and HTTPS checked. Record the result; otherwise say "not deployed".

## Known gaps / do not overclaim

- No authentication or accounts; anyone with a session ID can read its history. Booking lookup by raw ID without `session_id` is public.
- Rate limiting is in-memory, per worker, and keyed on the client host; behind a proxy this depends on whether trusted proxy headers are configured. It resets on restart.
- SQLite + local media: single instance only. Compose runs two Uvicorn workers; each has its own limiter, and SQLite serializes writes.
- No Alembic/schema migrations; `create_all` only creates missing tables.
- Media is stored, not understood or served: no image diagnosis, OCR, audio transcription, video analysis, admin UI, or `/media/` route.
- No TLS/HSTS in the app; terminate TLS at the edge/proxy.
- No frontend unit/e2e tests; `docs/CHECKLIST.md` is a manual audit.
- No live deployment or verified URL; `ec2-nginx.conf` and the deployment guide are prepared but unexecuted.

## Change rules

- Add or update a test with every behavior change; never weaken an existing assertion to make a change pass. Keep all 37 green.
- Keep endpoints, trailing slashes, status codes, and JSON field names stable; update `docs/API.md` and `src/api.ts` together.
- Keep AI behind `ai_service.py`, deterministic fallbacks intact, and `ai_used` honest.
- Never log or return keys, raw provider errors, tracebacks, or filesystem paths; keep the secret-leak test green.
- Do not add a framework, database, queue, or auth system without an explicit plan and user approval. The FastAPI migration is complete; do not restart it.
- For model changes, add a real migration strategy first; do not assume `create_all` updates an existing database.
- Keep the prototype honest: no fabricated image analysis, metrics, live URLs, prices, ETAs, or guaranteed outcomes. Business claims stay marked unverified.
- Update README/docs/checklist when behavior, setup, or deployment changes, and keep this file current.
- Preserve the contact flows and `CONTACT` values; keep the site mobile-first and accessible.
