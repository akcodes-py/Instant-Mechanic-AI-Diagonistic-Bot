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
# 89 passed, ~82% coverage; all Groq calls mocked, no model files required
# (dispatch engine adds 16 JUnit 5 tests via: cd dispatch-service && ./gradlew test)
```
No live AI calls in tests — every provider interaction is patched. ML tests use empty paths/missing files, so they exercise the safe fallbacks without downloading models.

## Evaluation mapping
Code quality (typed frontend, layered FastAPI backend), API design (Pydantic schemas, status codes, validation), UX (mobile-first, emergency CTAs always visible), error handling (useful messages, no stack leaks), deployment (S3 + CloudFront + AWS docs), DB design (FK sessions/messages/uploads/diagnoses/bookings, UUIDs, indexes), minimal AI usage (rules first, Groq only when useful).

## Project Design Record (PDR) — Instant Mechanic: H3 Local Mechanic Dispatch & Fleet System

> **Status of this document:** the PDR below is reproduced in full, organized into
> sections, exactly as specified. It is the approved design (see
> `docs/adr/ADR-001-h3-dispatch-platform.md`). The implementation exists **locally
> and is not deployed**; the honest item-by-item status is in section 8. Everything
> in the chatbot sections above still applies — the dispatch platform is additive.

### 1. Executive Summary

We are evolving Instant Mechanic from a standalone AI car diagnostic chatbot into a real-time **Local Mechanic Supply & Dispatch Management System** for Delhi NCR (Gurugram). Modeled directly on how Uber manages its driver fleet, the platform connects stranded drivers with nearby, skill-matched local mechanics using Uber's **H3 Hexagonal Spatial Index**, event-driven **Kafka** streaming, **ML-ranked ETA dispatch**, **Polyglot Persistence**, and **atomic concurrency locks**.

### 2. Core Objectives

1. **Real-Time Local Mechanic Fleet Management** — track live mechanic availability (`ONLINE`, `OFFLINE`, `ON_JOB`), GPS telemetry, and tool/skill capabilities (e.g. `battery_jumpstart`, `tyre_puncture`, `engine_overheat`, `towing`) with zero "ghost" mechanics.
2. **O(1) Hexagonal Matching** — replace slow geospatial table scans with H3 hexagonal ring expansion (k=1 → 2 → 3) and ML-ranked ETA/skill scoring.
3. **Zero Double-Dispatch** — guarantee via Redis distributed locks and MS SQL atomic state transitions (`WHERE status = 'SEARCHING'`) that no mechanic is ever assigned two breakdowns simultaneously.
4. **Rich Diagnostic Context for Mechanics** — persist chat threads, uploaded dashboard photos (in S3), and YOLO11n bounding boxes in MongoDB so the assigned mechanic sees the exact fault and photo before leaving the garage.
5. **Safe Real-World Fallback** — preserve deterministic safety rules and escalate automatically to the existing emergency hotline (`+91 6392077642`) if no mechanic accepts within the cascade window.
6. **Production Engineering Rigor** — enforce Clean Architecture, SOLID principles, TDD (JUnit 5 + pytest), TeamCity CI, and Puppet deployment — while staying runnable on an 8GB RAM machine.

### 3. Complete Technology Stack (What & Why)

| Layer | Technology | Exact Purpose |
|:--|:--|:--|
| Dispatch & Fleet Service | Kotlin (Ktor) | Lightweight, coroutine-based microservice handling telemetry ingestion, H3 ring matching, 15s offer cascades, and WebSockets. |
| AI & ML Service | Python (FastAPI) | Existing YOLO11n warning-light detector, DeBERTa-v3 symptom classifier, Groq fallback, ONNX Runtime, plus a new scikit-learn / LightGBM ETA & Mechanic Ranker. |
| Frontend & Simulator | Bun + ReactJS (TS) | Existing Driver chat/diagnosis UI (`src/`) + a new `/mechanic` simulator console with `h3-js` hexagonal map overlays. |
| Event Bus | Redpanda (Kafka) | Kafka-compatible event streaming (~250 MB RAM locally) decoupling telemetry, AI diagnosis, and dispatch events. |
| Locks & Hot Cache | Redis | 15-second exclusive offer locks (`SET NX EX`), hot H3 hex supply sets, and WebSocket Pub/Sub fan-out. |
| Batch Analytics | PySpark + Hadoop | Reads/writes partitioned Parquet trip archives to compute hex-level breakdown heatmaps and retrain ETA models. |
| CI/CD & Deployment | Git, TeamCity, Puppet | Verified `.teamcity/settings.kts` (Kotlin DSL) CI pipeline and Docker-tested `puppet/manifests/site.pp` for EC2 + Nginx provisioning. |

### 4. Polyglot Database Architecture

Each database handles the exact workload it was designed for, linked across services by a single shared UUID (`booking_id`):

| Store | Workload |
|:--|:--|
| **MongoDB** (Chat & Media Metadata) | `chat_messages` (conversation threads, AI provider metadata) and `uploaded_media` (S3 photo/audio/video URLs, YOLO11n bounding boxes, confidence scores). Raw binaries live in AWS S3 (or local volume in dev), never as blobs in MongoDB. |
| **MS SQL Server** (Transactional State) | ACID store for verified mechanic profiles, skill registries, bookings, invoices, and atomic job state machines (`WHERE status = 'SEARCHING'`). |
| **Apache Cassandra** (Live GPS Telemetry) | High-write-throughput store partitioned by `h3_res8_index` with a 60-second TTL. Lost 4G / closed app ⇒ the presence row auto-expires. |
| **Redis** (In-Memory Locks & Cache) | 15-second exclusive offer locks (`lock:mechanic:{id}`) and hot ONLINE mechanic sets per H3 hex. |
| **Hadoop / Parquet** (Cold Archive) | Completed trips, rejection logs, and NHTSA datasets for PySpark batch feature engineering. |

### 5. H3 Spatial Strategy & Kafka Event Loop

**Hexagonal grid resolutions**

| Resolution | Approx. edge | Use |
|:--|:--|:--|
| 8 | ~460 m | Live mechanic presence in Cassandra and ring-expansion dispatch (k=1 = 7 hexes, k=2 = 19 hexes, k=3 = 37 hexes). |
| 7 | ~1.22 km | Kafka partition key (localizes city-zone traffic), React supply/demand heatmaps, PySpark analytics. |

**End-to-end event flow**

1. `mechanic.telemetry.updated` — Mechanic console sends GPS ping every 5s → Ktor computes H3 Res-8/7 → writes to Cassandra (60s TTL) + Redis hot set.
2. `diagnosis.completed` — FastAPI saves chat/photo metadata to MongoDB, runs deterministic/YOLO/DeBERTa/Groq diagnosis, and publishes `required_skill`, `urgency`, and `photo_url` to Kafka.
3. `dispatch.offer.created` — Ktor queries Cassandra for online mechanics in k=1 hexes matching `required_skill`, ranks them via FastAPI's ML ETA model (with a `<300ms` nearest-distance fallback), acquires a 15-second Redis lock, and pushes an exclusive offer via WebSocket.
4. `dispatch.offer.accepted` / `rejected` — On accept, MS SQL executes an atomic conditional update (`WHERE status = 'SEARCHING'`). On decline/timeout, Ktor releases the Redis lock and cascades to the next mechanic (or expands to k=2, k=3, then emergency hotline fallback).
5. `job.status.changed` — Streams `EN_ROUTE → ARRIVED → IN_REPAIR → COMPLETED` to both React portals and archives the final record to Parquet for PySpark.

### 6. Clean Architecture, SOLID & TDD Standards

Inside `dispatch-service/` (Kotlin Ktor), core business logic has **zero framework or database imports**:

- **Single Responsibility (SRP):** `DispatchStateMachine` only enforces valid job transitions; `TelemetryHandler` only ingests GPS pings.
- **Open/Closed (OCP):** `RankingStrategy` interface allows swapping `NearestAvailableStrategy` and `MlEtaRankingStrategy` without modifying the dispatch orchestrator.
- **Dependency Inversion (DIP):** Core use cases depend only on ports (`SpatialIndex`, `PresenceStore`, `OfferLockStore`, `BookingRepository`), enabling 100% in-memory JUnit 5 + MockK TDD runs alongside the existing pytest suite.

### 7. Real-Life 8GB RAM Strategy & Phased Delivery

To run smoothly on an 8GB RAM laptop without OOM crashes, offload managed DBs to free cloud tiers (MongoDB Atlas M0, DataStax Astra DB for Cassandra, Azure SQL Free Tier for MS SQL) and run Redpanda + Redis + Kotlin Ktor + FastAPI + Bun (React) locally (~1.5–2 GB RAM total).

- **Phase 1 — Infrastructure & Contracts:** lightweight `docker-compose.yml`, shared `contracts/` Kafka JSON schemas, Cassandra H3 table, MS SQL atomic booking schema, MongoDB indexes.
- **Phase 2 — Kotlin Dispatch Engine (TDD):** scaffold `dispatch-service/` with Clean Architecture, H3 `GridDisk` ring expansion, Redis 15s lock cascade, JUnit 5 + MockK tests.
- **Phase 3 — MongoDB, ML & Live Hex UI:** add Motor (MongoDB) + S3/local upload to FastAPI, wire Kafka producer + scikit-learn ETA ranker, build the React `/mechanic` console with `h3-js`.
- **Phase 4 — PySpark & DevOps:** add `spark-jobs/` Parquet demand/retraining script, `.teamcity/settings.kts`, Docker-verified Puppet manifests.

### 8. Implementation Status (honest, as of 2026-11-22)

| PDR item | Status |
|:--|:--|
| Contracts, H3 conventions, DB schemas, Compose foundation (Phase 1) | ✅ implemented locally |
| Kotlin Ktor dispatch engine, H3 cascade, Redis locks, atomic claim, 16 JUnit tests (Phase 2) | ✅ implemented locally |
| `/rank/eta`, Kafka producer, MongoDB metadata, `/mechanic` console (Phase 3) | ✅ implemented locally |
| `spark-jobs/hex_demand.py`, `.teamcity/settings.kts`, `puppet/manifests/site.pp` (Phase 4) | ✅ artifacts authored locally |
| Redpanda + Redis + MongoDB + MinIO actually started end-to-end | ⬜ not yet run |
| Cassandra / MS SQL real adapters under load | ⬜ opt-in `heavy` profile, unverified |
| TeamCity applied / Puppet applied to a host | ⬜ config artifacts only, no server |
| Live URL, uptime, smoke test, verified ETA accuracy | ⬜ none — **not deployed** |
| Bun for frontend | ⬜ npm used instead (Bun not installed locally) |

Local gates: `python -m pytest -q` (89 passed), `cd dispatch-service && ./gradlew test` (16 passed), `npm run lint/typecheck/build`, `docker compose config --quiet`. Start the stack with `docker compose up --build`; add `--profile heavy` for Cassandra/MS SQL on a larger machine. Details: `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/adr/ADR-001-h3-dispatch-platform.md`.

## Live URLs
Not deployed yet — see docs/DEPLOYMENT.md for S3 + CloudFront (frontend) and AWS EC2 (backend) steps. No URLs fabricated.

## Business claims
Metrics (30,000+ cars, 4.9★, 20-min SLA) are shown as business claims with an "unverified" note, per audit. Contact flows preserved: `tel:+916392077642`, `https://wa.me/916392077642`, `atul@instantmechanic.online`, Sector 75 Gurugram.
