# TimescaleDB Use Cases for Homelab

**Status**: Ideas / Planning
**Database**: PostgreSQL 16 + TimescaleDB (running in K3s `database` namespace)
**Related**: [Production PostgreSQL Setup](/docs/blog/2025-12-15-production-postgres-k3s-timescaledb.md)

---

## Why TimescaleDB Over Prometheus?

| Capability | Prometheus | TimescaleDB |
|------------|------------|-------------|
| High-cardinality data | Explodes memory | Handles fine |
| Long-term retention | Expensive | Cheap with compression |
| Ad-hoc SQL queries | PromQL only | Full SQL |
| JOINs with other data | No | Yes |
| Continuous aggregates | Recording rules (limited) | Automatic rollups |
| Event/log correlation | Not designed for | Natural fit |

**Rule of thumb**: Use TimescaleDB when you need to:
- Store high-cardinality data (per-device, per-user, per-session)
- Run ad-hoc analytical queries
- Join time-series with relational data
- Keep years of history cheaply

---

## Use Case 1: Frigate Detection Events

**Priority**: High
**Effort**: Medium
**Value**: Detection pattern analysis, security insights

### Problem
Frigate stores events in SQLite. Limited query capability. Can't easily answer:
- "How many people at front door between 6-8 PM last month?"
- "Which camera has most false positives?"
- "Average detection duration by zone?"

### Solution
Pipe Frigate MQTT events to TimescaleDB.

```sql
CREATE TABLE frigate_events (
    time TIMESTAMPTZ NOT NULL,
    event_id TEXT,
    camera TEXT,
    label TEXT,
    score FLOAT,
    zone TEXT[],
    duration_sec FLOAT,
    has_clip BOOLEAN,
    has_snapshot BOOLEAN
);
SELECT create_hypertable('frigate_events', 'time');

-- Continuous aggregate: daily rollup
CREATE MATERIALIZED VIEW frigate_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS day,
    camera,
    label,
    COUNT(*) as detections,
    AVG(score) as avg_score,
    AVG(duration_sec) as avg_duration
FROM frigate_events
GROUP BY day, camera, label
WITH NO DATA;

-- Refresh policy
SELECT add_continuous_aggregate_policy('frigate_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

### Implementation
1. Create MQTT to PostgreSQL bridge (Node-RED, Telegraf, or custom script)
2. Subscribe to `frigate/events`
3. Insert to TimescaleDB
4. Build Grafana dashboard

### Grafana Panels
- Detections heatmap by hour/day
- Detection count by camera/label
- False positive rate (low score detections)
- Average duration trends

---

## Use Case 2: Crucible Storage Metrics

**Priority**: High
**Effort**: Medium
**Value**: Storage performance visibility (Oximeter doesn't export to Prometheus)

### Problem
Crucible uses Oximeter (pushes to ClickHouse), not Prometheus. No visibility into:
- Read/write IOPS per volume
- Latency percentiles
- Bandwidth utilization
- Downstairs health

### Solution
Collect metrics from Crucible and store in TimescaleDB.

```sql
CREATE TABLE crucible_io (
    time TIMESTAMPTZ NOT NULL,
    host TEXT,
    volume TEXT,
    read_iops BIGINT,
    write_iops BIGINT,
    read_bytes BIGINT,
    write_bytes BIGINT,
    latency_p50_us FLOAT,
    latency_p99_us FLOAT
);
SELECT create_hypertable('crucible_io', 'time');

CREATE TABLE crucible_downstairs (
    time TIMESTAMPTZ NOT NULL,
    host TEXT,
    port INTEGER,
    region TEXT,
    state TEXT,  -- 'active', 'faulted', 'offline'
    generation BIGINT
);
SELECT create_hypertable('crucible_downstairs', 'time');
```

### Implementation
1. Write collector script on proper-raptor
2. Parse `/proc` or Crucible logs for I/O stats
3. Cron job to insert every minute
4. Grafana dashboard

### Grafana Panels
- IOPS over time by volume
- Latency heatmap
- Bandwidth utilization
- Downstairs status matrix

---

## Use Case 3: Home Assistant State History

**Priority**: Medium
**Effort**: Low (HA has built-in PostgreSQL support)
**Value**: Complex queries, long-term retention, correlation

### Problem
HA uses SQLite by default. Limited retention. Can't query:
- "When was garage door open while nobody home?"
- "Correlate temperature with HVAC runtime"
- "Energy usage patterns over 2 years"

### Solution
Configure HA to use external PostgreSQL recorder.

```yaml
# configuration.yaml
recorder:
  db_url: postgresql://postgres:PASSWORD@postgres-postgresql.database.svc.cluster.local:5432/homeassistant
  purge_keep_days: 365
  commit_interval: 5
```

```sql
-- HA creates tables automatically, but we can add hypertable
SELECT create_hypertable('states', 'last_updated',
    migrate_data => true,
    if_not_exists => true);

-- Example query: Garage open while away
SELECT s.last_updated, s.state
FROM states s
JOIN states p ON time_bucket('1 minute', s.last_updated) = time_bucket('1 minute', p.last_updated)
WHERE s.entity_id = 'cover.garage_door' AND s.state = 'open'
AND p.entity_id = 'group.family' AND p.state = 'not_home';
```

### Implementation
1. Create `homeassistant` database in PostgreSQL
2. Update HA configuration.yaml
3. Restart HA
4. Historical data migrates automatically

### Grafana Panels
- Entity state timeline
- Presence correlation
- Climate control efficiency

---

## Use Case 4: Network Flow Data

**Priority**: Low
**Effort**: High
**Value**: Per-device bandwidth analysis

### Problem
Prometheus can't handle high-cardinality data like per-MAC-address metrics. Router/switch flow data explodes Prometheus.

### Solution
Store NetFlow/sFlow data in TimescaleDB.

```sql
CREATE TABLE network_flows (
    time TIMESTAMPTZ NOT NULL,
    src_mac TEXT,
    dst_mac TEXT,
    src_ip INET,
    dst_ip INET,
    protocol INTEGER,
    bytes BIGINT,
    packets BIGINT
);
SELECT create_hypertable('network_flows', 'time');

-- Compression for long-term storage
ALTER TABLE network_flows SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'src_mac'
);
SELECT add_compression_policy('network_flows', INTERVAL '7 days');
```

### Implementation
1. Configure router to export NetFlow/sFlow
2. Run flow collector (goflow2, pmacct)
3. Insert to TimescaleDB
4. Build per-device bandwidth dashboard

---

## Use Case 5: Power/Energy Tracking

**Priority**: Medium
**Effort**: Low
**Value**: Cost analysis, efficiency tracking

### Problem
Smart plugs report power, but correlating with time-of-use rates requires SQL.

### Solution
Store power readings with rate calculations.

```sql
CREATE TABLE power_readings (
    time TIMESTAMPTZ NOT NULL,
    device TEXT,
    watts FLOAT,
    voltage FLOAT
);
SELECT create_hypertable('power_readings', 'time');

-- Continuous aggregate: hourly energy
CREATE MATERIALIZED VIEW energy_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS hour,
    device,
    AVG(watts) as avg_watts,
    AVG(watts) / 1000.0 as kwh  -- approximate
FROM power_readings
GROUP BY hour, device;

-- Cost calculation view
CREATE VIEW energy_cost AS
SELECT
    hour,
    device,
    kwh,
    CASE
        WHEN EXTRACT(hour FROM hour) BETWEEN 16 AND 21 THEN kwh * 0.35  -- peak
        ELSE kwh * 0.12  -- off-peak
    END as cost_usd
FROM energy_hourly;
```

---

## Use Case 6: CI/CD Pipeline Metrics

**Priority**: Low (work-related)
**Effort**: Medium
**Value**: Build performance analysis

### Problem
ADO pipeline metrics are hard to query historically. Want to track:
- Stage duration trends
- Failure rates by pipeline
- Queue time patterns

### Solution
Collect pipeline run data via ADO API, store in TimescaleDB.

```sql
CREATE TABLE pipeline_runs (
    time TIMESTAMPTZ NOT NULL,
    pipeline_id INTEGER,
    pipeline_name TEXT,
    build_id INTEGER,
    result TEXT,
    duration_sec FLOAT,
    queue_time_sec FLOAT,
    stages JSONB
);
SELECT create_hypertable('pipeline_runs', 'time');
```

---

## Implementation Priority

| Use Case | Priority | Effort | Quick Win? |
|----------|----------|--------|------------|
| Frigate events | High | Medium | Yes - MQTT bridge |
| Crucible metrics | High | Medium | Yes - fills monitoring gap |
| HA state history | Medium | Low | Yes - just config change |
| Power tracking | Medium | Low | Yes - if smart plugs exist |
| Network flows | Low | High | No - complex setup |
| CI/CD metrics | Low | Medium | No - work-related |

## Next Steps

1. Start with **Frigate events** - most immediate value
2. Add **Crucible metrics** - unique data not available elsewhere
3. Consider **HA PostgreSQL recorder** - easy win

---

**Tags**: timescaledb, postgresql, prometheus, grafana, frigate, crucible, home-assistant, metrics, time-series
