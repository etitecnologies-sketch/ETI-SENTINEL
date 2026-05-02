DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS timescaledb;
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB extension not available; continuing without hypertables/compression.';
END $$;

CREATE TABLE IF NOT EXISTS clients (
  id               SERIAL PRIMARY KEY,
  name             TEXT NOT NULL UNIQUE,
  document         TEXT DEFAULT '',
  email            TEXT DEFAULT '',
  phone            TEXT DEFAULT '',
  address          TEXT DEFAULT '',
  city             TEXT DEFAULT '',
  state            TEXT DEFAULT '',
  plan             TEXT DEFAULT 'basic',
  status           TEXT DEFAULT 'active',
  telegram_token   TEXT DEFAULT '',
  telegram_chat_id TEXT DEFAULT '',
  alert_email      TEXT DEFAULT '',
  wa_instance      TEXT DEFAULT '',
  wa_token         TEXT DEFAULT '',
  wa_number        TEXT DEFAULT '',
  notes            TEXT DEFAULT '',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id            SERIAL PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'client',
  access_level  SMALLINT NOT NULL DEFAULT 1,
  permissions   JSONB DEFAULT '{}'::jsonb,
  client_id     INT REFERENCES clients(id) ON DELETE CASCADE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'client';
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_level SMALLINT NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '{}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS client_id INT REFERENCES clients(id) ON DELETE CASCADE;

DO $$
BEGIN
  UPDATE users SET access_level = 3 WHERE role = 'superadmin' AND (access_level IS NULL OR access_level < 3);
EXCEPTION
  WHEN undefined_column THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS hosts (
  id         SERIAL PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS devices (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL,
  hostname      TEXT UNIQUE,
  token         TEXT NOT NULL UNIQUE,
  client_id     INT REFERENCES clients(id) ON DELETE CASCADE,
  ip_address    TEXT DEFAULT '',
  device_type   TEXT DEFAULT 'server',
  tags          TEXT[] DEFAULT '{}',
  description   TEXT DEFAULT '',
  location      TEXT DEFAULT '',
  status        TEXT DEFAULT 'pending',
  last_seen     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  snmp_community TEXT DEFAULT 'public',
  snmp_version   TEXT DEFAULT '2c',
  ssh_user       TEXT,
  ssh_port       INT DEFAULT 22,
  monitor_ping   BOOLEAN DEFAULT TRUE,
  monitor_snmp   BOOLEAN DEFAULT FALSE,
  monitor_agent  BOOLEAN DEFAULT TRUE,
  ai_enabled     BOOLEAN DEFAULT FALSE,
  ddns_address   TEXT DEFAULT '',
  monitor_port   INT DEFAULT 0,
  notes          TEXT DEFAULT '',
  mac_address    TEXT DEFAULT '',
  serial_number  TEXT DEFAULT ''
);

ALTER TABLE devices ADD COLUMN IF NOT EXISTS client_id INT REFERENCES clients(id) ON DELETE CASCADE;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ip_address TEXT DEFAULT '';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS device_type TEXT DEFAULT 'server';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS snmp_community TEXT DEFAULT 'public';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS snmp_version TEXT DEFAULT '2c';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ssh_user TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ssh_port INT DEFAULT 22;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_ping BOOLEAN DEFAULT TRUE;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_snmp BOOLEAN DEFAULT FALSE;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_agent BOOLEAN DEFAULT TRUE;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ddns_address TEXT DEFAULT '';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_port INT DEFAULT 0;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT '';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS mac_address TEXT DEFAULT '';
ALTER TABLE devices ADD COLUMN IF NOT EXISTS serial_number TEXT DEFAULT '';

CREATE TABLE IF NOT EXISTS metrics (
  time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  host_id         INT REFERENCES hosts(id) ON DELETE CASCADE,
  host            TEXT NOT NULL,
  device_id       INT REFERENCES devices(id) ON DELETE SET NULL,
  cpu             DOUBLE PRECISION NOT NULL DEFAULT 0,
  memory          DOUBLE PRECISION NOT NULL DEFAULT 0,
  disk_used       DOUBLE PRECISION NOT NULL DEFAULT 0,
  disk_total      DOUBLE PRECISION NOT NULL DEFAULT 0,
  disk_percent    DOUBLE PRECISION NOT NULL DEFAULT 0,
  net_rx_bytes    BIGINT NOT NULL DEFAULT 0,
  net_tx_bytes    BIGINT NOT NULL DEFAULT 0,
  latency_ms      DOUBLE PRECISION NOT NULL DEFAULT 0,
  uptime_seconds  BIGINT NOT NULL DEFAULT 0,
  load_avg        DOUBLE PRECISION NOT NULL DEFAULT 0,
  processes       INT NOT NULL DEFAULT 0,
  temperature     DOUBLE PRECISION NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'online',
  solar_voltage   DOUBLE PRECISION NOT NULL DEFAULT 0,
  battery_voltage DOUBLE PRECISION NOT NULL DEFAULT 0,
  battery_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
  charge_current  DOUBLE PRECISION NOT NULL DEFAULT 0,
  load_current    DOUBLE PRECISION NOT NULL DEFAULT 0
);

ALTER TABLE metrics ADD COLUMN IF NOT EXISTS disk_used DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS disk_total DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS net_rx_bytes BIGINT NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS net_tx_bytes BIGINT NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'online';
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS solar_voltage DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS battery_voltage DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS battery_percent DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS charge_current DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS load_current DOUBLE PRECISION NOT NULL DEFAULT 0;

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
CREATE INDEX IF NOT EXISTS idx_metrics_device_time ON metrics (device_id, time DESC);

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
  name       TEXT NOT NULL,
  expression TEXT NOT NULL,
  threshold  FLOAT NOT NULL,
  enabled    BOOLEAN NOT NULL DEFAULT TRUE,
  client_id  INT REFERENCES clients(id) ON DELETE CASCADE,
  device_type TEXT,
  tags       TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE triggers ADD COLUMN IF NOT EXISTS client_id INT REFERENCES clients(id) ON DELETE CASCADE;
ALTER TABLE triggers ADD COLUMN IF NOT EXISTS device_type TEXT;
ALTER TABLE triggers ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE triggers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
  IF (SELECT COUNT(*) FROM triggers) = 0 THEN
    INSERT INTO triggers (name, expression, threshold) VALUES
      ('High CPU',       'cpu',         80),
      ('High Memory',    'memory',      85),
      ('High Disk',      'disk_percent',90),
      ('High Latency',   'latency_ms',  500),
      ('High Load',      'load_avg',    5);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS alerts (
  id          BIGSERIAL PRIMARY KEY,
  trigger_id  INT REFERENCES triggers(id) ON DELETE CASCADE,
  device_id   INT REFERENCES devices(id) ON DELETE SET NULL,
  host        TEXT NOT NULL,
  expression  TEXT NOT NULL,
  value       FLOAT NOT NULL,
  threshold   FLOAT NOT NULL,
  alert_type  TEXT NOT NULL DEFAULT 'threshold',
  fired_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  client_id   INT REFERENCES clients(id) ON DELETE CASCADE
);

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS client_id INT REFERENCES clients(id) ON DELETE CASCADE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_type TEXT NOT NULL DEFAULT 'threshold';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_alerts_fired ON alerts (fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_device_open ON alerts (device_id) WHERE resolved_at IS NULL;

CREATE TABLE IF NOT EXISTS events (
  id             BIGSERIAL PRIMARY KEY,
  time           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device_id      INT REFERENCES devices(id) ON DELETE CASCADE,
  event_type     TEXT NOT NULL,
  channel        INT DEFAULT 0,
  description    TEXT,
  severity       TEXT DEFAULT 'info',
  source         TEXT DEFAULT 'push',
  raw_event_type TEXT DEFAULT '',
  payload        JSONB DEFAULT '{}'::jsonb,
  is_read        BOOLEAN DEFAULT FALSE
);

DO $$
DECLARE
  payload_type TEXT;
BEGIN
  SELECT format_type(a.atttypid, a.atttypmod)
    INTO payload_type
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = current_schema()
    AND c.relname = 'events'
    AND a.attname = 'payload'
    AND a.attnum > 0
    AND NOT a.attisdropped;

  IF payload_type IS NOT NULL AND payload_type <> 'jsonb' THEN
    ALTER TABLE events ADD COLUMN IF NOT EXISTS payload_jsonb JSONB DEFAULT '{}'::jsonb;
    BEGIN
      EXECUTE 'UPDATE events SET payload_jsonb = payload::jsonb WHERE payload IS NOT NULL AND payload <> ''''';
    EXCEPTION
      WHEN OTHERS THEN
        EXECUTE 'UPDATE events SET payload_jsonb = jsonb_build_object(''raw'', payload) WHERE payload IS NOT NULL AND payload <> ''''';
    END;
    ALTER TABLE events DROP COLUMN payload;
    ALTER TABLE events RENAME COLUMN payload_jsonb TO payload;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_events_time ON events (time DESC);

CREATE TABLE IF NOT EXISTS onvif_configs (
  device_id   INT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
  enabled     BOOLEAN DEFAULT FALSE,
  host        TEXT NOT NULL DEFAULT '',
  port        INT DEFAULT 80,
  username    TEXT DEFAULT '',
  password_enc TEXT DEFAULT '',
  channel_map JSONB DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rtsp_configs (
  device_id   INT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
  enabled     BOOLEAN DEFAULT FALSE,
  username    TEXT DEFAULT '',
  password_enc TEXT DEFAULT '',
  streams     JSONB DEFAULT '[]'::jsonb,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS discovered_devices (
  id          BIGSERIAL PRIMARY KEY,
  agent_id    TEXT NOT NULL DEFAULT '',
  client_id   INT REFERENCES clients(id) ON DELETE SET NULL,
  ip_address  TEXT NOT NULL DEFAULT '',
  mac_address TEXT DEFAULT '',
  hostname    TEXT DEFAULT '',
  vendor      TEXT DEFAULT '',
  guess_type  TEXT DEFAULT '',
  open_ports  INT[] DEFAULT '{}',
  onvif_xaddrs TEXT DEFAULT '',
  device_id   INT REFERENCES devices(id) ON DELETE SET NULL,
  raw         JSONB DEFAULT '{}'::jsonb,
  first_seen  TIMESTAMPTZ DEFAULT NOW(),
  last_seen   TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_devices_agent_ip ON discovered_devices (agent_id, ip_address);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_client ON discovered_devices (client_id);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_last_seen ON discovered_devices (last_seen DESC);

CREATE TABLE IF NOT EXISTS solar_inverters (
  id                SERIAL PRIMARY KEY,
  client_id         INT REFERENCES clients(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  brand             TEXT NOT NULL,
  model             TEXT DEFAULT '',
  location          TEXT DEFAULT '',
  capacity_kwp      FLOAT DEFAULT 0,
  tariff_kwh        FLOAT DEFAULT 0.85,
  status            TEXT DEFAULT 'active',
  growatt_user      TEXT DEFAULT '',
  growatt_pass      TEXT DEFAULT '',
  growatt_plant_id  TEXT DEFAULT '',
  fronius_ip        TEXT DEFAULT '',
  fronius_device_id INTEGER DEFAULT 1,
  solarman_token    TEXT DEFAULT '',
  solarman_app_id   TEXT DEFAULT '',
  solarman_logger_sn TEXT DEFAULT '',
  sma_user          TEXT DEFAULT '',
  sma_pass          TEXT DEFAULT '',
  sma_plant_id      TEXT DEFAULT '',
  goodwe_user       TEXT DEFAULT '',
  goodwe_pass       TEXT DEFAULT '',
  goodwe_station_id TEXT DEFAULT '',
  huawei_user       TEXT DEFAULT '',
  huawei_pass       TEXT DEFAULT '',
  huawei_station_id TEXT DEFAULT '',
  saj_user          TEXT DEFAULT '',
  saj_pass          TEXT DEFAULT '',
  saj_plant_id      TEXT DEFAULT '',
  api_url           TEXT DEFAULT '',
  api_key           TEXT DEFAULT '',
  api_type          TEXT DEFAULT '',
  notes             TEXT DEFAULT '',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_solar_inverters_client ON solar_inverters (client_id);
CREATE INDEX IF NOT EXISTS idx_solar_inverters_status ON solar_inverters (status);

CREATE TABLE IF NOT EXISTS solar_metrics (
  time              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  inverter_id       INT REFERENCES solar_inverters(id) ON DELETE CASCADE,
  client_id         INT REFERENCES clients(id) ON DELETE CASCADE,
  power_w           FLOAT DEFAULT 0,
  energy_today_kwh  FLOAT DEFAULT 0,
  energy_month_kwh  FLOAT DEFAULT 0,
  energy_total_kwh  FLOAT DEFAULT 0,
  voltage_pv        FLOAT DEFAULT 0,
  voltage_ac        FLOAT DEFAULT 0,
  current_ac        FLOAT DEFAULT 0,
  frequency_hz      FLOAT DEFAULT 50,
  temperature_c     FLOAT DEFAULT 0,
  revenue_today     FLOAT DEFAULT 0,
  revenue_month     FLOAT DEFAULT 0,
  revenue_total     FLOAT DEFAULT 0,
  inverter_status   TEXT DEFAULT 'unknown',
  fault_code        TEXT DEFAULT '',
  last_update       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_solar_metrics_time ON solar_metrics (inverter_id, time DESC);

CREATE OR REPLACE VIEW latest_metrics AS
SELECT DISTINCT ON (m.host)
  m.host,
  m.cpu,
  m.memory,
  m.disk_percent,
  m.net_rx_bytes,
  m.net_tx_bytes,
  m.latency_ms,
  m.uptime_seconds,
  m.load_avg,
  m.processes,
  m.temperature,
  m.status,
  m.time,
  m.device_id,
  d.name AS device_name,
  d.location,
  d.description
FROM metrics m
LEFT JOIN devices d ON m.device_id = d.id
WHERE m.time > NOW() - INTERVAL '5 minutes'
ORDER BY m.host, m.time DESC;
