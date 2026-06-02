-- ETI SENTINEL — Migration: OTA e Feature Flags por Cliente
-- Executar no banco da Railway antes de fazer deploy desta versão.

-- 1. Coluna features em clients (JSONB — armazena feature flags por cliente)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS features JSONB DEFAULT '{}';

-- 2. Tabela de manifests OTA
CREATE TABLE IF NOT EXISTS ota_manifests (
  id           SERIAL PRIMARY KEY,
  version      VARCHAR(32)  NOT NULL,
  download_url TEXT         NOT NULL,
  sha256       VARCHAR(64)  NOT NULL,
  notes        TEXT         DEFAULT '',
  required     BOOLEAN      DEFAULT false,
  active       BOOLEAN      DEFAULT true,
  created_at   TIMESTAMP    DEFAULT NOW()
);

-- 3. Índice para busca rápida do manifest ativo mais recente
CREATE INDEX IF NOT EXISTS idx_ota_manifests_active
  ON ota_manifests (active, created_at DESC);

-- Verificação
SELECT 'features column' AS check, data_type
  FROM information_schema.columns
 WHERE table_name='clients' AND column_name='features'
UNION ALL
SELECT 'ota_manifests table', table_name::text
  FROM information_schema.tables
 WHERE table_name='ota_manifests';
