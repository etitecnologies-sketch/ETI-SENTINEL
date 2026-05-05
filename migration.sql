-- ============================================================
--  ETI SENTINEL — Migration: device_type, tags, config fields
--  Execute: docker compose exec db psql -U monitor -d monitoring -f /migration.sql
-- ============================================================

-- ── Tabela devices: novos campos ────────────────────────────
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

-- ── Tabela triggers: novos campos ────────────────────────────
ALTER TABLE triggers
  ADD COLUMN IF NOT EXISTS device_type TEXT,
  ADD COLUMN IF NOT EXISTS tags        TEXT[] DEFAULT '{}';

-- ── Índices úteis ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(device_type);
CREATE INDEX IF NOT EXISTS idx_devices_tags ON devices USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_devices_ip   ON devices(ip_address);

-- ── Tipos disponíveis (comentário referência) ─────────────
-- server | camera | router | switch | routerboard | eti_sentinel
-- firewall | printer | iot | workstation | other

SELECT 'Migration ETI SENTINEL concluída com sucesso!' as resultado;
