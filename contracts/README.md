# Contracts (contract-first)

All services communicate through these versioned schemas. A shared `booking_id` UUID links
one breakdown across MongoDB, the transactional store, Cassandra, Redis, Kafka, and Parquet.

- `events/` — Kafka JSON Schemas (draft 2020-12). Every event uses the envelope in
  `events/common.schema.json`. Topic names equal the `event_type` values.
- `db/` — DDL/index definitions for Cassandra (Res-8 presence, 60 s TTL), MS SQL
  (transactional mechanics/skills/bookings/invoices + atomic state transition), MongoDB
  (chat threads + media metadata), and the Redis key layout.
- `h3.md` — H3 resolution, ring sizes, Kafka partition key, and coordinate conventions.

## Event topics

| Topic | Producer | Meaning |
|:--|:--|:--|
| `mechanic.telemetry.updated` | Ktor dispatch | GPS/status/skills ping (every 5 s) |
| `diagnosis.completed` | FastAPI | diagnosis persisted; skill, urgency, photo ready |
| `dispatch.offer.created` | Ktor dispatch | exclusive 15 s offer pushed to one mechanic |
| `dispatch.offer.accepted` | Ktor dispatch | mechanic accepted; state transition attempted |
| `dispatch.offer.rejected` | Ktor dispatch | mechanic declined or offer timed out |
| `job.status.changed` | Ktor dispatch | EN_ROUTE → ARRIVED → IN_REPAIR → COMPLETED |

## Rules

1. Never remove or rename a field in a released schema; add optional fields with a default.
2. `schema_version` is incremented on every structural change.
3. No secrets, raw provider errors, filesystem paths, or PII beyond the fields shown here.
4. Media binaries live in S3/MinIO or a local volume; events carry only object keys/URLs.
5. All timestamps are ISO-8601 UTC. All coordinates are WGS84 `lat`/`lon` decimals.
