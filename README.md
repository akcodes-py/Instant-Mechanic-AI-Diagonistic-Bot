# Instant Mechanic — AI Diagnostics & H3 Mechanic Dispatch Platform

**Delhi NCR car-care platform:** an AI diagnostic chatbot (chat → diagnosis → booking) extended with a real-time, Uber-style local mechanic supply-and-dispatch engine built on H3 hexagons, Kafka streaming, Redis locks and polyglot persistence.

| | |
|:--|:--|
| **Status** | Production-grade implementation delivered across all four PDR phases; automated gates green. Deployment runbook included in [section 12](#12-deployment-runbook). Record live evidence after your deployment. |
| **Coverage** | Delhi NCR (National Capital Region). Gurugram / Sector 75 is the simulator demo zone, not the boundary. |
| **Automated gates** | 89 pytest passed (~82% coverage) · 16 JUnit 5 + MockK passed · frontend lint/typecheck/build clean · Compose config valid |
| **Repository** | https://github.com/akcodes-py/Instant-Mechanic-AI-Diagonistic-Bot |

---

## 1. Highlights

- **Two runtimes, one contract surface.** Python 3.12/FastAPI AI service + Java 21/Kotlin Ktor dispatch service, coupled through six versioned Kafka JSON schemas keyed by a shared `booking_id` UUID.
- **H3 hexagonal dispatch.** Res-8 (~460 m) presence and `gridDisk` ring cascade (k=1 → 7, k=2 → 19, k=3 → 37 hexes); Res-7 (~1.22 km) Kafka partition key and heatmap grid.
- **No double dispatch.** 15 s Redis `SET NX EX` exclusive offer locks (Lua compare-and-delete release) **plus** an atomic `UPDATE … WHERE status IN ('SEARCHING','OFFERED')` state transition. A second accept cannot win.
- **No ghost mechanics.** 60 s TTL on presence rows and hot supply sets; a mechanic who stops pinging disappears automatically.
- **Clean Architecture with strict boundaries.** The Kotlin `domain/` package has zero framework/database imports; use cases depend only on ports, so the entire dispatch engine is testable in memory with fake adapters.
- **Five-workload polyglot persistence.** MongoDB (chat/media metadata), MS SQL (transactional state), Cassandra (GPS telemetry), Redis (locks/cache), Parquet + PySpark (cold analytics), with local adapters behind the same ports for an 8 GB laptop.
- **Safety is deterministic and infra-independent.** Rules engine and unsafe-symptom override run before/after AI; if no mechanic accepts the full cascade, the system escalates to the emergency hotline `+91 6392077642`. No broker or database failure can block it.
- **Honest AI.** Deterministic rules first; Groq only for nuanced cases; ML off by default. `/rank/eta` reports `model_used: false` and uses nearest-distance when no model is mounted. No fabricated detections, ETAs, metrics or URLs.

---

## 2. Architecture at a glance

```
Driver (React SPA)                         Mechanic Simulator (/mechanic, h3-js)
  chat / diagnosis / booking                 telemetry 5 s · offers · job status · WS
        |                                             |
        v                                             v
FastAPI :8000  ──diagnosis.completed(Kafka)──▶ Redpanda ──▶ Kotlin Ktor :8081
  triage rules → ML (opt-in) → Groq                |            H3 Res-8 gridDisk rings
  /rank/eta (LightGBM/sklearn or fallback)          |            15 s Redis offer locks
  MongoDB metadata · S3/MinIO media keys           |            atomic MS SQL/SQLite claim
        |                                          v
        └──────────── Parquet archive ──▶ PySpark hex demand + ETA retraining

Redis  : hot supply sets + locks      Cassandra : 60 s TTL telemetry (heavy profile)
MS SQL : transactional state (heavy profile)      Nginx/TLS terminated at the edge
```

Full explanation: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 3. Repository layout

```
src/                      React 19 + Vite 8 + TypeScript 7 + Tailwind 4 driver UI
  api.ts                  typed driver API client (VITE_API_URL)
  dispatchApi.ts          typed dispatch client (VITE_DISPATCH_URL)
  spatial.ts              shared H3 helpers (h3-js)
  components/MechanicConsole.tsx   /mechanic simulator
backend/app/              FastAPI AI service (7 driver endpoints + ranker + context)
  routes/                 health, chat, upload, diagnosis, booking, history, ranker, context
  services/               triage, ai_service, media, session_store, vision, nlp,
                          calibration, onnx, spatial, ranker, event_bus, mongo_store
  tests/                  89 pytest tests (no live AI calls, no model files)
dispatch-service/         Kotlin Ktor engine — Clean Architecture (domain / adapters)
  src/main/kotlin/.../domain    model, port, usecase, events (framework-free)
  src/main/kotlin/.../adapters  spatial, ranking, redis, booking, kafka, http
  src/test/kotlin/...           16 JUnit 5 + MockK tests (in memory)
contracts/                Kafka JSON schemas, DB DDL, Redis keys, H3 conventions
spark-jobs/               PySpark / pandas Parquet demand job
.teamcity/settings.kts    TeamCity Kotlin DSL (artifact, not applied)
puppet/manifests/site.pp  EC2 + Nginx provisioning (artifact, not applied)
docs/                     API, ARCHITECTURE, DEPLOYMENT, CHECKLIST, adr/ADR-001
docker-compose.yml        full local stack (+ `--profile heavy` for Cassandra/MS SQL)
```

---

## 4. Core capabilities

### Driver flow (unchanged, still green)
Chat with deterministic follow-ups and polite non-car rejection · image/audio/video upload with magic-byte and size validation · structured diagnosis with rules → optional local classifier → Groq → safe fallback · real booking records and history · emergency CTAs always visible.

### Dispatch flow (additive)
Live telemetry → H3 ring matching → skill + ETA ranking → exclusive 15 s offer → accept/reject → `EN_ROUTE → ARRIVED → IN_REPAIR → COMPLETED` → Parquet archive, with hotline escalation after k=3.

### Service endpoints

| Service | Method & path | Purpose |
|:--|:--|:--|
| FastAPI | `POST /api/chat/` | chat, follow-ups, non-car rejection (200 + `action: reject`) |
| FastAPI | `POST /api/upload/` | validated media storage; real detections only when a model ran |
| FastAPI | `POST /api/diagnosis/` | structured, persisted preliminary diagnosis |
| FastAPI | `POST /api/booking/` · `GET /api/booking/<id>/` | booking create / detail |
| FastAPI | `GET /api/history/<session_id>/` | conversation + diagnosis history |
| FastAPI | `GET /api/health/` | health check |
| FastAPI | `POST /rank/eta` | mechanic ETA ranking for Ktor |
| FastAPI | `GET /api/context/<session_id>/` | MongoDB diagnostic context (503 when unavailable) |
| Ktor | `GET /api/dispatch/health/` | dispatch liveness |
| Ktor | `POST /api/dispatch/telemetry/` | GPS/status ping (every 5 s) |
| Ktor | `POST /api/dispatch/bookings/` · `POST /api/dispatch/bookings/<id>/dispatch/` | create booking / run cascade |
| Ktor | `POST /api/dispatch/offers/<id>/accept/` · `/reject/` | atomic claim / release |
| Ktor | `POST /api/dispatch/jobs/<id>/status/` | validated state transition |
| Ktor | `WS /api/dispatch/ws/jobs/<id>` | live job events |

Contract details: [`docs/API.md`](docs/API.md) and [`contracts/`](contracts/).

### Kafka event topics

| Topic | Producer | Meaning |
|:--|:--|:--|
| `mechanic.telemetry.updated` | Ktor | GPS/status/skills ping |
| `diagnosis.completed` | FastAPI | diagnosis persisted; skill, urgency, photo ready |
| `dispatch.offer.created` | Ktor | exclusive 15 s offer |
| `dispatch.offer.accepted` / `rejected` | Ktor | mechanic response / timeout |
| `job.status.changed` | Ktor | status transitions and escalation |

---

## 5. Quick start

### Full local stack (Docker)

```bash
cd instant-mechanic
copy .env.example .env          # fill GROQ_API_KEY only on a server; never commit
docker compose up --build
# FastAPI   http://localhost:8000/api/health/
# Ktor      http://localhost:8081/api/dispatch/health/
# Redpanda  localhost:9092   Redis :6379   MongoDB :27017   MinIO :9000 / :9001
# Frontend  npm run dev  ->  http://localhost:5173  (set VITE_DISPATCH_URL=http://localhost:8081)
```
On a machine with more than 8 GB RAM: `docker compose --profile heavy up` also starts Cassandra and MS SQL.

### Backend only (no Docker)

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt
copy .env.example .env
cd backend && python -m uvicorn app.main:app --reload --port 8000
```
Tables are created on startup (`create_all`); there is no migration step. The app reads the repo-root `.env`. ML wheels are CPU-only; model files are never committed and ML is off by default.

### Dispatch engine only

```powershell
cd dispatch-service
.\gradlew.bat test    # 16 in-memory JUnit 5 tests
.\gradlew.bat run     # http://localhost:8081
```
Java 21 is required; the Gradle wrapper downloads Gradle 8.10.2 on first run.

### Frontend gates

```bash
npm install
npm run dev            # http://localhost:5173
npm run lint           # 0 errors (2 pre-existing React warnings)
npm run typecheck      # clean
npm run build          # dist/
```

---

## 6. Configuration reference

All settings are typed in [`backend/app/config.py`](backend/app/config.py); the tracked template is [`.env.example`](.env.example).

| Variable | Default | Notes |
|:--|:--|:--|
| `DEBUG` | `True` | `DJANGO_DEBUG` accepted as legacy alias |
| `DATABASE_URL` | `sqlite+aiosqlite:///./db.sqlite3` | `MEDIA_ROOT` for local uploads |
| `CORS_ORIGINS` | localhost:5173, 127.0.0.1:5173 | `CORS_ALLOW_ALL` is debug-only |
| `GROQ_API_KEY` | empty | server-side only; empty = deterministic mode |
| `ENABLE_ML_INFERENCE` | `False` | vision/NLP off; every failure falls back safely |
| `H3_PRESENCE_RESOLUTION` / `H3_ZONE_RESOLUTION` | `8` / `7` | dispatch and heatmap grids |
| `DISPATCH_MAX_RING` / `OFFER_TTL_SECONDS` | `3` / `15` | cascade depth and exclusive lock TTL |
| `REDPANDA_BROKERS` / `REDIS_URL` | `localhost:9092` / `redis://localhost:6379/0` | overridden by Compose |
| `MONGODB_URL` / `ENABLE_MONGO` | `mongodb://localhost:27017` / `False` | metadata store; off by default |
| `MINIO_ENDPOINT` / `MINIO_BUCKET` | `localhost:9000` / `instant-mechanic-media` | local S3 |
| `ETA_MODEL_PATH` | empty | mounted model; empty → nearest-distance fallback |
| `VITE_API_URL` / `VITE_DISPATCH_URL` | `:8000` / `:8081` | frontend only; no secrets in `VITE_*` |

---

## 7. AI, ML and safety

- **Deterministic first:** validation → relevance gate → rule-based follow-ups → rule-based diagnosis (battery, overheating, airbag, tyre, brakes, fuel, keys, noise).
- **Groq only when useful:** vague-but-car-related messages and nuanced diagnosis; structured JSON is validated; rate limit → 503, timeout → 504, other failures fall back without leaking details. `GROQ_API_KEY` never reaches the frontend.
- **Optional ML:** YOLO11n warning-light detection, DeBERTa-v3 symptom classifier, ONNX helpers, temperature scaling + conformal routing. All lazy, off by default, safe on any failure.
- **Safety override:** smoke, fire, burning smell, fuel leak, brake failure or steering loss force `critical` urgency and do-not-drive guidance. No ML or LLM result can bypass it.
- **No fabrication:** uploads are "received, not auto-analyzed" unless a real model returned detections; no invented prices, ETAs, mechanic names, or outcomes.

---

## 8. Data and concurrency model

| Concern | Mechanism |
|:--|:--|
| Session identity | Anonymous UUID capability; no auth in this prototype |
| Offer-time presence | Redis hot supply sets (authoritative for offers), 60 s TTL |
| Telemetry history | Cassandra `mechanic_presence` partitioned by `h3_res8_index`, 60 s TTL |
| Assignment authority | Atomic conditional update on the transactional store + filtered unique index on active mechanics |
| Mutual exclusion | Redis `SET NX EX 15` lock with Lua compare-and-delete release |
| Rich context | MongoDB `chat_messages` / `uploaded_media`; binaries in S3/MinIO, never as blobs |
| Cold analytics | Partitioned Parquet → PySpark heatmaps and ETA retraining |
| TLS | Terminated at CloudFront/Nginx; the apps do not redirect HTTP themselves |

---

## 9. Testing strategy

- **89 pytest tests** — API, AI services, ML fallbacks, spatial helpers, ranker, event bus, context endpoint. Every provider interaction is mocked; no API key, model file or broker is needed.
- **16 JUnit 5 + MockK tests** — state machine, telemetry handling, ring cascade, skill filtering, lock contention, escalation, atomic accept, rejection, illegal transitions. All in memory via fake ports.
- **Frontend gates** — `lint`, `typecheck`, `build`.
- **Manual simulator audit** — [`docs/CHECKLIST.md`](docs/CHECKLIST.md) covers telemetry, offer, accept/decline, status transitions and hotline fallback.
- **CI** — `.github/workflows/ci.yml` runs backend pytest + Docker build, dispatch `./gradlew test`, Compose validation, and frontend gates on Python 3.12 / Java 21 / Node 20.

---

## 10. Verification gates

Run locally before any deployment:

| Gate | Command | Expected |
|:--|:--|:--|
| Backend tests | `python -m pytest -q` | 89 passed, ~82% coverage |
| Dispatch tests | `cd dispatch-service && ./gradlew test` | 16 passed |
| Frontend | `npm run lint && npm run typecheck && npm run build` | clean (2 known warnings) |
| Compose | `docker compose config --quiet` | exit 0 |
| API smoke | `curl http://localhost:8000/api/health/` | `{"status":"ok",...}` |
| Dispatch smoke | `curl http://localhost:8081/api/dispatch/health/` | `{"message":"ok"}` |
| Flow smoke | chat → diagnosis → booking → telemetry → dispatch → accept → status | 200/201 responses, one winning accept, `ESCALATED` path reachable |

These gates have been run locally. **They are not a live deployment result** — see below.

---

## 11. Known limitations

- No authentication; a session ID is the only capability. Booking lookup by raw ID without `session_id` is public in this prototype.
- In-memory rate limiting is per process and resets on restart; behind a proxy it depends on trusted headers.
- SQLite + local media = single instance; Compose runs two Uvicorn workers with serialized writes.
- No Alembic: `create_all` creates missing tables only.
- Redis/SQLite stand in locally for Cassandra/MS SQL behind the same ports; real adapters are authored but not load-tested.
- ML weights, calibration data and a trained ETA model are not included. No accuracy numbers are claimed.
- No frontend unit/e2e tests; the checklist is a manual audit.
- TeamCity and Puppet files are configuration artifacts; no servers were available to apply them.
- **No live deployment, URL, uptime figure or production smoke result exists.**

---

## 12. Deployment runbook

Use this **runbook** to bring the platform live. A deployment is recorded as complete once the host passes the checks in [Verification gates](#10-verification-gates) with real output and timestamps.

1. **Frontend:** `npm run build` → upload `dist/` to S3 → serve through CloudFront with 403/404 → `/index.html` rewrites; set `CORS_ORIGINS` on the API to the CloudFront domain.
2. **Backend + dispatch:** provision EC2 (Ubuntu, Docker + Compose), place the repo, copy `.env.example` → `.env` with real secrets, run `docker compose up --build -d`. TLS terminates at Nginx (`ec2-nginx.conf`) or the load balancer.
3. **Managed stores (production shape):** MongoDB Atlas M0, DataStax Astra (Cassandra), Azure SQL Free (MS SQL), AWS S3 for media. Point `MONGODB_URL`, `REDPANDA_BROKERS`, `REDIS_URL`, and DB connection strings at those services. For a local-only 8 GB demo use the default Compose profile.
4. **CI/CD:** TeamCity project in [`.teamcity/settings.kts`](.teamcity/settings.kts); host provisioning in [`puppet/manifests/site.pp`](puppet/manifests/site.pp). Both are artifacts pending a real server.
5. **Record the evidence:** health checks, one full flow, CORS check, TLS check, URL, and UTC timestamp — then update section 11 and the status line at the top of this README.

Step-by-step guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## 13. Project Design Record (PDR) — Instant Mechanic: H3 Local Mechanic Dispatch & Fleet System

> **Status of this document:** the PDR below is reproduced in full, organized into
> sections, exactly as specified. It is the approved design (see
> [`docs/adr/ADR-001-h3-dispatch-platform.md`](docs/adr/ADR-001-h3-dispatch-platform.md)).
> The implementation exists **locally and is not deployed**; the honest item-by-item
> status is in section 8 below. Everything in the capability sections above still
> applies — the dispatch platform is additive to the original chatbot.

### 1. Executive Summary

**Coverage: the whole Delhi NCR (National Capital Region).** Gurugram / Sector 75 is only the simulator's demo grid, not the boundary of the system.

We are evolving Instant Mechanic from a standalone AI car diagnostic chatbot into a real-time **Local Mechanic Supply & Dispatch Management System** for Delhi NCR. Modeled directly on how Uber manages its driver fleet, the platform connects stranded drivers with nearby, skill-matched local mechanics using Uber's **H3 Hexagonal Spatial Index**, event-driven **Kafka** streaming, **ML-ranked ETA dispatch**, **Polyglot Persistence**, and **atomic concurrency locks**.

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
| 7 | ~1.22 km | Kafka partition key (localizes city-zone traffic across Delhi NCR), React supply/demand heatmaps, PySpark analytics. |

The grid is a region-wide NCR design: Res-8 drives fine-grained dispatch anywhere in the NCR, Res-7 partitions Kafka traffic by local zone. The demo centre below is a single sample zone, not a coverage limit.

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

### 8. Implementation Summary

All four PDR phases were delivered:

- **Phase 1 — Infrastructure & Contracts.** Built `contracts/` with six versioned Kafka JSON schemas, Cassandra/MS SQL/MongoDB DDL, Redis key layout and H3 conventions; implemented Res-8/Res-7 spatial helpers in Python and TypeScript; defined the full Compose topology (Redpanda, Redis, MongoDB, MinIO, FastAPI, Ktor, plus opt-in `heavy` profiles for Cassandra and MS SQL).
- **Phase 2 — Kotlin Dispatch Engine.** Implemented a Clean Architecture Ktor service with framework-free domain core, `DispatchStateMachine`, `TelemetryHandler`, `OfferCascade`, H3 `gridDisk` ring expansion, 15 s Redis exclusive locks with Lua release, atomic assignment, ranking strategy interface, Kafka producer, WebSocket fan-out, and 16 in-memory JUnit 5 + MockK tests.
- **Phase 3 — AI Service & Live Hex UI.** Added `/rank/eta` with nearest-distance fallback, best-effort `diagnosis.completed` Kafka publishing, MongoDB chat/media metadata with `/api/context/{session_id}/`, and the React `/mechanic` simulator with `h3-js` hex overlays, 5 s telemetry, offers, job status and hotline escalation.
- **Phase 4 — Analytics & DevOps.** Authored `spark-jobs/hex_demand.py` (PySpark with a pandas fallback), `.teamcity/settings.kts`, and `puppet/manifests/site.pp`; extended CI with dispatch tests and Compose validation.

Automated gates: `python -m pytest -q` → 89 passed (~82% coverage); `cd dispatch-service && ./gradlew test` → 16 passed; `npm run lint/typecheck/build` → clean; `docker compose config --quiet` → valid. Start the platform with `docker compose up --build`; use `--profile heavy` for Cassandra and MS SQL.

**Verification boundary:** the above is the locally implemented and tested scope. Host provisioning, managed-store load testing, TeamCity/Puppet application and the public live URL are deployment activities — follow [section 12](#12-deployment-runbook) and record real results there.

---

## 14. Documentation index

- [`docs/API.md`](docs/API.md) — endpoint and status-code contract
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — layers, data and dispatch topology
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — AWS deployment guide (not executed)
- [`docs/CHECKLIST.md`](docs/CHECKLIST.md) — manual website and simulator audit
- [`docs/adr/ADR-001-h3-dispatch-platform.md`](docs/adr/ADR-001-h3-dispatch-platform.md) — architecture decision record
- [`contracts/`](contracts/) — event schemas, DB DDL, Redis keys, H3 rules
- [`AGENTS.md`](AGENTS.md) — repository rules and source-of-truth notes

## 15. Business claims & contact

Metrics shown on the marketing site (30,000+ cars, 4.9★, 20-minute SLA) are **unverified business claims**, not measured results. Contact flows are preserved: `tel:+916392077642`, `https://wa.me/916392077642`, `atul@instantmechanic.online`, Sector 75, Gurugram (Delhi NCR).
