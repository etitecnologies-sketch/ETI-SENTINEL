-- ============================================================
--  ETI SENTINEL — Migration v2
--  Execute: docker compose exec db psql -U monitor -d monitoring -f /migration_v2.sql
-- ============================================================

-- ── devices: novos campos ────────────────────────────────────
ALTER TABLE devices
  ADD COLUMN IF NOT EXISTS device_type    TEXT    DEFAULT 'other',
  ADD COLUMN IF NOT EXISTS ip_address     TEXT,
  ADD COLUMN IF NOT EXISTS tags           TEXT[]  DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS snmp_community TEXT    DEFAULT 'public',
  ADD COLUMN IF NOT EXISTS snmp_version   TEXT    DEFAULT '2c',
  ADD COLUMN IF NOT EXISTS ssh_user       TEXT,
  ADD COLUMN IF NOT EXISTS ssh_port       INTEGER DEFAULT 22,
  ADD COLUMN IF NOT EXISTS monitor_ping   BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS monitor_snmp   BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS monitor_agent  BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS notes          TEXT    DEFAULT '';

-- ── triggers: novos campos ────────────────────────────────────
ALTER TABLE triggers
  ADD COLUMN IF NOT EXISTS device_type TEXT,
  ADD COLUMN IF NOT EXISTS tags        TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ DEFAULT NOW();

-- ── Índices ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_devices_type   ON devices(device_type);
CREATE INDEX IF NOT EXISTS idx_devices_tags   ON devices USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_devices_ip     ON devices(ip_address);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
CREATE INDEX IF NOT EXISTS idx_alerts_type    ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_fired   ON alerts(fired_at DESC);

-- ── TimescaleDB: compressão e retenção (se disponível) ──────
DO $$
BEGIN
  -- Compressão automática após 7 dias
  BEGIN
    PERFORM add_compression_policy('metrics', INTERVAL '7 days');
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
  -- Retenção de 30 dias
  BEGIN
    PERFORM add_retention_policy('metrics', INTERVAL '30 days');
  EXCEPTION WHEN OTHERS THEN NULL;
  END;
END $$;

SELECT 'Migration ETI SENTINEL v2 concluída com sucesso!' as resultado;
