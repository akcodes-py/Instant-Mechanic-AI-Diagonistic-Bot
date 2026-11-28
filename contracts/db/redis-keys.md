# Redis key layout

| Key | Type | TTL | Purpose |
|:--|:--|:--|:--|
| `lock:mechanic:{mechanic_id}` | string | 15 s | Exclusive offer lock (`SET NX EX 15`). Only the owner may release it (compare-and-delete via Lua). |
| `lock:booking:{booking_id}` | string | 15 s | Prevents two cascade runners for the same breakdown. |
| `presence:{h3_res8}:{mechanic_id}` | string (JSON) | 60 s | Local stand-in for Cassandra presence row. |
| `supply:{h3_res8}:{skill}` | set | 60 s | Hot ONLINE supply set; members are mechanic IDs. |
| `offer:{offer_id}` | hash | 15 s | Offer state mirror for WebSocket fan-out / PubSub. |
| `pubsub:job:{booking_id}` | pub/sub channel | — | Pushes `job.status.changed` to connected React clients. |

## Lock invariant

A mechanic is offered at most one job at a time:

```
acquire = SET lock:mechanic:{id} {offer_id} NX EX 15
release = if GET == offer_id then DEL   (Lua, atomic)
```

The Redis lock is mutual exclusion only. The authoritative state change is the
conditional MSSQL/SQLite `UPDATE ... WHERE status = 'SEARCHING'`.
