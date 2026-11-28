# ADR-001: H3 Local Mechanic Dispatch & Fleet System

- Status: Accepted
- Date: 2026-11-22
- Supersedes: the single-process scope recorded in `AGENTS.md` and `docs/ARCHITECTURE.md`

## Context

`instant-mechanic` began as an assignment/portfolio chatbot: React + Vite + TypeScript frontend, FastAPI + async SQLAlchemy + SQLite backend, with deterministic triage, optional ML (YOLO warning lights, DistilBERT/DeBERTa symptom classification) and a Groq fallback. It is a working, tested monolith (72 passing tests at the time of writing) with no auth, a single SQLite database, local media, and no queue or background jobs.

The product now needs to evolve into a real-time local mechanic supply-and-dispatch system for the Delhi NCR region, modelled on ride-hailing fleet operations (Gurugram / Sector 75 is the simulator demo zone, not the coverage boundary): live mechanic telemetry, H3 hexagonal supply discovery, skill/ETA ranking, exclusive offers with hard timeouts, and an atomic job state machine.

`AGENTS.md` contains binding rules that prohibit adding new databases, queues, frameworks, or new deployment tooling without an explicit plan and user approval. The Project Design Record (PDR) for the H3 dispatch platform is that explicit approval. This ADR records what is being superseded, what is preserved, and the decisions taken so the rules and the code do not silently diverge.

## Decision

1. **Evolve additively.** The existing `chat -> diagnosis -> booking` flow, its 7 endpoints, SQLite storage, and all existing tests remain intact and green. Dispatch is a new layer that consumes diagnosis events; it does not replace the working prototype in a big-bang rewrite. This protects the deterministic safety net and the demo that the assignment brief evaluates.

2. **Introduce an event-driven, polyglot architecture** with separate services and stores:
   - Kotlin/Ktor `dispatch-service/` for telemetry ingestion, H3 ring expansion, offer cascade, WebSockets, and Redis locks.
   - Python/FastAPI remains the AI/ML service (existing deterministic triage, YOLO, NLP, Groq) and gains an ETA/mechanic ranker.
   - Redpanda (Kafka-compatible) is the event bus; Redis holds 15-second exclusive offer locks and hot supply sets.
   - MongoDB stores chat/media metadata and YOLO bounding boxes; transactional state (mechanics, skills, bookings, job state machine) targets MS SQL Server; Cassandra stores live GPS telemetry with a 60-second TTL; Parquet/Hadoop is the cold archive for PySpark analytics.

3. **Keep Clean Architecture strict in the Kotlin service.** Core use cases depend only on ports (`SpatialIndex`, `PresenceStore`, `OfferLockStore`, `BookingRepository`, `RankingStrategy`). Framework, database, and broker code lives in adapters. This allows 100% in-memory JUnit 5 + MockK tests.

4. **Local-first, production-adapters-second.** The full polyglot stack does not fit in 8 GB of RAM. Local development runs Redpanda, Redis, MongoDB, and MinIO (local S3) in Docker, with SQLite standing in for MS SQL and Redis standing in for Cassandra behind the same ports. Cassandra and MS SQL are declared as opt-in Compose profiles with their real schemas checked in, so the production adapters are reviewable and testable without forcing an OOM on a laptop. Cloud free tiers (Atlas M0, Astra, Azure SQL Free, S3) remain the documented deployment target for a later phase.

5. **Safety stays deterministic and infra-independent.** Unsafe symptoms always force critical urgency and do-not-drive guidance. If no mechanic accepts across the k=1 -> k=2 -> k=3 cascade, the system escalates to the existing emergency hotline (`+91 6392077642`). No queue, lock, database, or ML failure may block the deterministic chat/diagnosis/booking flow or the hotline fallback.

6. **Deployment tooling is authored as artifacts, not run locally.** `.teamcity/settings.kts` and `puppet/manifests/site.pp` are committed and Docker-verified where practical, but no live TeamCity or Puppet server is available on this machine. Nothing in this ADR claims a deployed URL, uptime, or smoke result that was not actually tested.

7. **H3 conventions.** Resolution 8 (~460 m edge) is the live presence and ring-dispatch grid (k=1 = 7 hexes, k=2 = 19, k=3 = 37). Resolution 7 (~1.22 km edge) is the Kafka partition key and the React/PySpark supply/demand heatmap grid.

8. **Source of truth.** Redis hot sets are authoritative for *offer-time presence*; Cassandra is the historical/audit telemetry store. Assignment authority is the atomic conditional update in the transactional store (`WHERE status = 'SEARCHING'`). Redis locks provide mutual exclusion only. This separation is what makes "no ghost mechanics" and "no double dispatch" honest, testable claims rather than slogans.

## Consequences

- `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `README.md`, `AGENTS.md`, and `docs/CHECKLIST.md` must be updated in the same changes that introduce each phase.
- New dependencies: `h3` (Python), `h3-js` (frontend), `motor`, `minio`, `kafka-python-ng`, scikit-learn/LightGBM (already available), Kotlin + Gradle wrapper (dispatch service).
- The test suite grows: existing pytest tests stay green; new pytest tests cover contracts, spatial helpers, and adapters (all mocked, no live services); new JUnit 5 + MockK tests cover the Kotlin core in memory.
- CI gains a Kotlin build/test step and Compose config validation. TeamCity/Puppet remain configuration artifacts until a server exists.
- Known gap: Python is 3.14 locally while CI/Docker use 3.12; new ML dependencies must be pinned and verified in both. LightGBM/sklearn/pandas/pyarrow are already present on 3.14 here.
