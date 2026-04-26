DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS timescaledb;
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB extension not available; continuing without hypertables/compression.';
END $$;

CREATE TABLE IF NOT EXISTS hosts (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS devices (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    hostname      TEXT UNIQUE,
    token         TEXT NOT NULL UNIQUE,
    description   TEXT    DEFAULT '',
    location      TEXT    DEFAULT '',
    status        TEXT    DEFAULT 'pending',
    last_seen     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    time            TIMESTAMPTZ      NOT NULL,
    host_id         INT              REFERENCES hosts(id) ON DELETE CASCADE,
    host            TEXT             NOT NULL,
    device_id       INT              REFERENCES devices(id) ON DELETE SET NULL,
    cpu             DOUBLE PRECISION NOT NULL DEFAULT 0,
    memory          DOUBLE PRECISION NOT NULL DEFAULT 0,
    disk_used       DOUBLE PRECISION NOT NULL DEFAULT 0,
    disk_total      DOUBLE PRECISION NOT NULL DEFAULT 0,
    disk_percent    DOUBLE PRECISION NOT NULL DEFAULT 0,
    net_rx_bytes    BIGINT           NOT NULL DEFAULT 0,
    net_tx_bytes    BIGINT           NOT NULL DEFAULT 0,
    latency_ms      DOUBLE PRECISION NOT NULL DEFAULT 0,
    uptime_seconds  BIGINT           NOT NULL DEFAULT 0,
    load_avg        DOUBLE PRECISION NOT NULL DEFAULT 0,
    processes       INT              NOT NULL DEFAULT 0,
    temperature     DOUBLE PRECISION NOT NULL DEFAULT 0
);

DO $$
BEGIN
  PERFORM create_hypertable('metrics', 'time', if_not_exists => TRUE);
EXCEPTION
  WHEN undefined_function THEN
    RAISE NOTICE 'create_hypertable() not available; continuing as plain Postgres table.';
  WHEN OTHERS THEN
    RAISE NOTICE 'Hypertable creation skipped due to missing TimescaleDB features.';
END $$;
CREATE INDEX IF NOT EXISTS idx_metrics_host_time ON metrics (host, time DESC);

DO $$
BEGIN
  ALTER TABLE metrics SET (
      timescaledb.compress,
      timescaledb.compress_segmentby = 'host'
  );
  PERFORM add_compression_policy('metrics', INTERVAL '7 days', if_not_exists => TRUE);
  PERFORM add_retention_policy('metrics', INTERVAL '90 days', if_not_exists => TRUE);
EXCEPTION
  WHEN undefined_object THEN
    RAISE NOTICE 'Compression/retention policies not available; continuing without TimescaleDB policies.';
  WHEN undefined_function THEN
    RAISE NOTICE 'Compression/retention functions not available; continuing without policies.';
  WHEN OTHERS THEN
    RAISE NOTICE 'Compression/retention policies skipped due to missing TimescaleDB features.';
END $$;

CREATE TABLE IF NOT EXISTS triggers (
    id         SERIAL PRIMARY KEY,
    name       TEXT    NOT NULL,
    expression TEXT    NOT NULL,
    threshold  FLOAT   NOT NULL,
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO triggers (name, expression, threshold) VALUES
    ('High CPU',       'cpu',         80),
    ('High Memory',    'memory',      85),
    ('High Disk',      'disk_percent',90),
    ('High Latency',   'latency_ms',  500),
    ('High Load',      'load_avg',    5)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS alerts (
    id          SERIAL PRIMARY KEY,
    trigger_id  INT   REFERENCES triggers(id) ON DELETE CASCADE,
    device_id   INT   REFERENCES devices(id) ON DELETE SET NULL,
    host        TEXT  NOT NULL,
    expression  TEXT  NOT NULL,
    value       FLOAT NOT NULL,
    threshold   FLOAT NOT NULL,
    alert_type  TEXT  NOT NULL DEFAULT 'threshold',
    fired_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_fired ON alerts (fired_at DESC);

CREATE OR REPLACE VIEW latest_metrics AS
SELECT DISTINCT ON (m.host)
    m.host, m.cpu, m.memory, m.disk_percent,
    m.net_rx_bytes, m.net_tx_bytes, m.latency_ms,
    m.uptime_seconds, m.load_avg, m.processes,
    m.temperature, m.time, m.device_id,
    d.name as device_name, d.location, d.description
FROM metrics m
LEFT JOIN devices d ON m.device_id = d.id
WHERE m.time > NOW() - INTERVAL '5 minutes'
ORDER BY m.host, m.time DESC;
