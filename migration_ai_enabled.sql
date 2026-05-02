-- ============================================================
--  ETI SENTINEL — Migration: ai_enabled per device
-- ============================================================

ALTER TABLE devices
  ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_devices_ai_enabled ON devices(ai_enabled);

SELECT 'Migration ai_enabled concluída com sucesso!' as resultado;

