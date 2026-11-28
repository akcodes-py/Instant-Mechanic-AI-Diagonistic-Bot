# Dispatch Service (Kotlin + Ktor)

Real-time H3 mechanic dispatch engine. Clean Architecture: the `domain` package
has **zero** framework, database or broker imports; adapters implement its ports.

## Layout

```
domain/model, domain/port, domain/usecase, domain/events   <- pure core
adapters/spatial    H3 res-8/7 index + ring expansion
adapters/ranking    NearestAvailableStrategy (fallback) | MlEtaRankingStrategy (FastAPI)
adapters/redis      15s exclusive offer locks, 60s hot supply sets
adapters/booking    SQLite stand-in for MS SQL (same atomic conditional update)
adapters/kafka      Redpanda producer
adapters/http       Ktor routes + WebSocket fan-out
```

## Run

```powershell
# Needs Java 21; the Gradle wrapper downloads Gradle 8.10.2 on first run.
.\gradlew.bat test                 # 16 JUnit 5 tests, all in-memory
.\gradlew.bat run                  # API on http://localhost:8081
```

With Docker Compose (from repo root): `docker compose up --build dispatch`.

## Environment

| Variable | Default | Purpose |
|:--|:--|:--|
| `REDIS_URL` | `redis://localhost:6379/0` | locks + hot supply sets |
| `REDPANDA_BROKERS` | `localhost:9092` | Kafka event bus |
| `AI_SERVICE_URL` | `http://localhost:8000` | Python ETA ranker |
| `ENABLE_ML_RANKING` | `false` | true = call the ranker, false = nearest-distance fallback |

## API

| Method | Path | Purpose |
|:--|:--|:--|
| GET | `/api/dispatch/health/` | liveness |
| POST | `/api/dispatch/telemetry/` | GPS/status ping (every 5 s) |
| POST | `/api/dispatch/bookings/` | create a booking in `SEARCHING` |
| POST | `/api/dispatch/bookings/{id}/dispatch/` | run k=1→2→3 cascade (or `ESCALATED` + hotline) |
| POST | `/api/dispatch/offers/{id}/accept/` | atomic claim |
| POST | `/api/dispatch/offers/{id}/reject/` | release + cascade again |
| POST | `/api/dispatch/jobs/{id}/status/` | validated status transition |
| WS | `/api/dispatch/ws/jobs/{id}` | live job events |

Contracts live in `../contracts/`. Local SQLite/Redis adapters implement the same
ports as the production MS SQL/Cassandra adapters (see `docs/adr/ADR-001`).
