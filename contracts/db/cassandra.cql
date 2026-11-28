-- Live mechanic GPS telemetry. Partitioned by H3 Res-8 hex, 60s TTL so a dead
-- app/4G drop auto-expires presence ("no ghost mechanics"). See contracts/h3.md.
CREATE KEYSPACE IF NOT EXISTS instant_mechanic
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE instant_mechanic;

CREATE TABLE IF NOT EXISTS mechanic_presence (
    h3_res8_index   text,
    mechanic_id     uuid,
    h3_res7_index   text,
    lat             double,
    lon             double,
    status          text,        -- ONLINE | OFFLINE | ON_JOB
    skills          set<text>,
    speed_kmh       double,
    heading         double,
    updated_at      timestamp,
    PRIMARY KEY ((h3_res8_index), mechanic_id)
) WITH default_time_to_live = 60
  AND comment = 'Live presence; 60s TTL. Redis hot sets are authoritative for offers.';

-- Kafka partition-keyed rollup used by the React heatmap / PySpark analytics.
CREATE TABLE IF NOT EXISTS hex_demand_res7 (
    h3_res7_index   text,
    bucket_start    timestamp,
    open_jobs       counter,
    PRIMARY KEY ((h3_res7_index), bucket_start)
);

-- Redis local stand-in (compose profile "local") implements the same port:
--   SETEX presence:{h3_res8}:{mechanic_id} 60 <json>
--   SADD  supply:{h3_res8}:{skill} <mechanic_id>   (EXPIRE 60)
