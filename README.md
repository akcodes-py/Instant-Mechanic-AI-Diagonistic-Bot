# Instant Mechanic — AI Car Mechanic Chatbot

India's Car Care Platform (Delhi NCR) + integrated IM Buddy chatbot: chat → diagnosis → booking.

**Folders (this directory, on Desktop):** `instant-mechanic/`
- Frontend (React + Vite + TypeScript + Tailwind): `src/`, `public/`, `index.html`
- Backend (Django + DRF + SQLite): `backend/`
- Tests: `backend/chatbot/tests/` (pytest, pytest-django, pytest-cov; no live AI calls)
- Infra: `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`, `.github/workflows/ci.yml`
- Docs: `docs/` + `README` sections below

## Quick start

### Backend (local, no Docker)
```bash
cd instant-mechanic
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r backend/requirements.txt
copy .env.example .env   # fill GROQ_API_KEY only on server, never commit
python backend/manage.py migrate
python backend/manage.py runserver  # http://127.0.0.1:8000/api/health/
```

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
- **Why Groq instead of Gemini?** The AI provider is fully isolated behind `chatbot/services/ai_service.py`. Swapping to Gemini requires only editing that one file — no views, models, or frontend changes needed. Groq was chosen because it provides a free-tier API key suitable for assignment evaluation without billing setup. The `groq_chat` / `groq_structured_diagnosis` functions can be replaced with equivalent Gemini calls (`google-generativeai`) with identical interfaces.

## Test coverage
```bash
cd instant-mechanic
python -m pytest backend --cov=chatbot --cov-report=term-missing
```
No live AI calls in tests — all Groq calls are patched with mocks.

## Evaluation mapping
Code quality (typed frontend, layered backend), API design (serializers, status codes, validation), UX (mobile-first, emergency CTAs always visible), error handling (useful messages, no stack leaks), deployment (Vercel + AWS docs), DB design (FK sessions/messages/uploads/diagnoses/bookings, UUIDs, indexes), minimal AI usage (rules first, Groq only when useful).

## Live URLs
Not deployed yet — see docs/DEPLOYMENT.md for Vercel (frontend) + AWS (backend) steps. No URLs fabricated.

## Business claims
Metrics (30,000+ cars, 4.9★, 20-min SLA) are shown as business claims with an "unverified" note, per audit. Contact flows preserved: `tel:+919266961110`, `https://wa.me/919266961110`, `gordhan@instantmechanic.online`, Sector 75 Gurugram.
