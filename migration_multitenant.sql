-- ============================================================
--  ETI SENTINEL Pro — Migration Multi-tenant
--  Execute: docker compose exec db psql -U monitor -d monitoring -f /migration_multitenant.sql
-- ============================================================

-- ── Tabela de clientes ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    document        TEXT,                    -- CNPJ/CPF
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    city            TEXT,
    state           TEXT,
    plan            TEXT DEFAULT 'basic',    -- basic | pro | enterprise
    status          TEXT DEFAULT 'active',   -- active | suspended | cancelled
    telegram_token  TEXT DEFAULT '',
    telegram_chat_id TEXT DEFAULT '',
    alert_email     TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Adicionar client_id nas tabelas existentes ───────────────
ALTER TABLE devices   ADD COLUMN IF NOT EXISTS client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE;
ALTER TABLE alerts    ADD COLUMN IF NOT EXISTS client_id INTEGER REFERENCES clients(id);
ALTER TABLE triggers  ADD COLUMN IF NOT EXISTS client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE;

-- ── Papel dos usuários ───────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS role      TEXT    DEFAULT 'superadmin';  -- superadmin | client
ALTER TABLE users ADD COLUMN IF NOT EXISTS client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE;

-- ── Índices ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_devices_client   ON devices(client_id);
CREATE INDEX IF NOT EXISTS idx_alerts_client    ON alerts(client_id);
CREATE INDEX IF NOT EXISTS idx_triggers_client  ON triggers(client_id);
CREATE INDEX IF NOT EXISTS idx_users_client     ON users(client_id);
CREATE INDEX IF NOT EXISTS idx_clients_status   ON clients(status);

-- ── Cliente padrão para devices existentes ───────────────────
INSERT INTO clients (name, plan, status, notes)
VALUES ('Minha Empresa', 'enterprise', 'active', 'Cliente padrão — dispositivos existentes')
ON CONFLICT DO NOTHING;

-- Vincular devices sem cliente ao cliente padrão
UPDATE devices SET client_id = (SELECT id FROM clients LIMIT 1) WHERE client_id IS NULL;
UPDATE triggers SET client_id = (SELECT id FROM clients LIMIT 1) WHERE client_id IS NULL;

-- Marcar usuário admin como superadmin
UPDATE users SET role = 'superadmin' WHERE client_id IS NULL;

SELECT 'Migration ETI SENTINEL Pro Multi-tenant concluída!' as resultado;
