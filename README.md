# Instant Mechanic — AI Car Mechanic Chatbot

India's Car Care Platform (Delhi NCR) + integrated IM Buddy chatbot: chat → diagnosis → booking.

**Folders (this directory, on Desktop):** `instant-mechanic/`
- Frontend (React + Vite + TypeScript + Tailwind): `src/`, `public/`, `index.html`
- Backend (FastAPI + SQLAlchemy + SQLite): `backend/`
- Tests: `backend/app/tests/` (pytest + httpx; no live AI calls)
- Infra: `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`, `.github/workflows/ci.yml`
- Docs: `docs/` + `README` sections below

> **Migration note:** the backend was migrated from Django/DRF to FastAPI + async SQLAlchemy. The 7 endpoints, status codes, and success JSON shapes are unchanged, so the frontend needs no code changes.

## Quick start

### Backend (local, no Docker)
```bash
cd instant-mechanic
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt
copy .env.example .env   # fill GROQ_API_KEY only on server, never commit
cd backend
python -m uvicorn app.main:app --reload --port 8000
# http://127.0.0.1:8000/api/health/
```
Tables are created automatically on startup; there is no `migrate` step. The app loads the repo-root `.env` (and a local `backend/.env` if present), so run Uvicorn from `backend/`.

The ML wheels are CPU-only and target the CI/Docker Python 3.12 runtime. Model files are not committed; with `ENABLE_ML_INFERENCE=False` (the default) the app and tests run fully deterministically without them.

### Frontend
```bash
npm install
echo VITE_API_URL=http://127.0.0.1:8000 > .env.local
npm run dev      # http://localhost:5173
npm run build    # production dist/
```

### Docker (backend)
```bash
docker compose up --build
# API: http://localhost:8000/api/health/ ; SQLite persists in sqlite-data volume (/data)
```

## API (see docs/API.md)
- `POST /api/chat/` — chat + follow-ups, polite rejection of non-car queries
- `POST /api/upload/` — image/audio/video (multipart `file` + `session_id`)
- `POST /api/diagnosis/` — structured preliminary diagnosis (persisted)
- `POST /api/booking/` — real booking record (no AI dependency)
- `GET /api/booking/<id>/` — retrieve booking (+ embedded diagnosis)
- `GET /api/history/<session_id>/` — conversation/diagnosis history
- `GET /api/health/` — health check

## AI usage (Groq, server-side only)
- Key from `GROQ_API_KEY` env. Never in frontend, images, workflows, or docs.
- Deterministic backend first: validation → relevance gate → rule-based follow-ups → rule-based diagnosis for common cases (battery, overheating, tyre, brakes, fuel, keys, noise).
- Groq (`GROQ_MODEL`, default `llama-3.3-70b-versatile`) only for nuanced symptom interpretation / follow-up phrasing. Structured JSON output is validated; timeouts/rate-limits return 504/503 with safe messages; missing key falls back to deterministic diagnosis.
- All provider calls are isolated in `backend/app/services/ai_service.py`. Swapping providers means editing that one file — no routes, models, or frontend changes needed.
- **Why Groq instead of Gemini?** Groq provides a free-tier API key suitable for assignment evaluation without billing setup. The `groq_chat` / `groq_structured_diagnosis` functions can be replaced with equivalent Gemini calls with identical interfaces.

## Optional ML inference (off by default)
`ENABLE_ML_INFERENCE=False` keeps the assignment flow deterministic. Set it to `True` and point the model paths at local files/directories to enable:

- `VISION_MODEL_PATH` — Ultralytics YOLO warning-light model. Class names come from the loaded model; image uploads get an optional dashboard-light check. The response includes `detections` (`label`, `confidence`, `box`, `reliable`) and `reliable_labels`. Default reliability is 0.40; `Check Engine`, `Electronic Stability Problem -ESP-`, and `Low Engine Oil Warning Light` require 0.50. If nothing reliable is found, the note asks for a clearer/closer photo or text instead of guessing. Audio/video are still stored only and never transcribed.
- `VISION_CONF` / `VISION_IMGSZ` — YOLO confidence and input size (defaults `0.25` / `960`); `iou=0.5` is fixed in the service.
- `NLP_MODEL_PATH` — local DistilBERT/DeBERTa symptom classifier. Diagnosis order is: deterministic rules → optional classifier (when rules miss) → Groq → safe generic fallback. A `calibration.json` inside the classifier directory (or its parent when the path is a file) enables temperature scaling + split conformal prediction; without it, only matches above 0.7 confidence are used.
- Every model load/inference failure logs only the error type and falls back safely. ML never decides relevance or safety, and unsafe-symptom handling still forces critical urgency and do-not-drive guidance.
- ONNX Runtime helpers (`backend/app/services/onnx_service.py`) support INT8-quantized models without changing the API. Latency depends on the model/hardware and is not benchmarked here. Models are mounted/copied at deploy time, never committed.

Dataset and calibration scripts (standalone, not imported by the app):
```bash
python backend/scripts/augment_nhtsa.py complaints.csv -o augmented.csv
python backend/scripts/create_calibration.py labelled.csv -o calibration.json
```

## Test coverage
```bash
cd instant-mechanic
python -m pytest -q
# 71 passed, 1 skipped (optional weights integration), ~81% coverage; all Groq calls mocked, no model files required
```
No live AI calls in tests — every provider interaction is patched. ML tests use empty paths/missing files, so they exercise the safe fallbacks without downloading models.

## Evaluation mapping
Code quality (typed frontend, layered FastAPI backend), API design (Pydantic schemas, status codes, validation), UX (mobile-first, emergency CTAs always visible), error handling (useful messages, no stack leaks), deployment (S3 + CloudFront + AWS docs), DB design (FK sessions/messages/uploads/diagnoses/bookings, UUIDs, indexes), minimal AI usage (rules first, Groq only when useful).

## Live URLs
Not deployed yet — see docs/DEPLOYMENT.md for S3 + CloudFront (frontend) and AWS EC2 (backend) steps. No URLs fabricated.

## Business claims
Metrics (30,000+ cars, 4.9★, 20-min SLA) are shown as business claims with an "unverified" note, per audit. Contact flows preserved: `tel:+916392077642`, `https://wa.me/916392077642`, `atul@instantmechanic.online`, Sector 75 Gurugram.
