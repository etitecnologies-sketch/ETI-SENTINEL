-- ============================================================
--  ETI SENTINEL Pro — Migration Solar
--  Execute: docker compose exec db psql -U monitor -d monitoring -f /migration_solar.sql
-- ============================================================

-- ── Tabela de inversores solares ─────────────────────────────
CREATE TABLE IF NOT EXISTS solar_inverters (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    brand           TEXT NOT NULL,   -- growatt | fronius | deye | solis | sma | canadian | goodwe | huawei | other
    model           TEXT DEFAULT '',
    location        TEXT DEFAULT '',
    capacity_kwp    FLOAT DEFAULT 0,  -- capacidade instalada em kWp
    tariff_kwh      FLOAT DEFAULT 0.85, -- tarifa R$/kWh para calcular receita
    status          TEXT DEFAULT 'active', -- active | inactive

    -- Credenciais por marca
    -- Growatt (ShineServer)
    growatt_user    TEXT DEFAULT '',
    growatt_pass    TEXT DEFAULT '',
    growatt_plant_id TEXT DEFAULT '',

    -- Fronius (API local na rede)
    fronius_ip      TEXT DEFAULT '',
    fronius_device_id INTEGER DEFAULT 1,

    -- Deye / Solis (SolarmanPV)
    solarman_token  TEXT DEFAULT '',
    solarman_app_id TEXT DEFAULT '',
    solarman_logger_sn TEXT DEFAULT '', -- número de série do logger

    -- SMA (Sunny Portal)
    sma_user        TEXT DEFAULT '',
    sma_pass        TEXT DEFAULT '',
    sma_plant_id    TEXT DEFAULT '',

    -- Goodwe (SEMS Portal)
    goodwe_user     TEXT DEFAULT '',
    goodwe_pass     TEXT DEFAULT '',
    goodwe_station_id TEXT DEFAULT '',

    -- Huawei (FusionSolar)
    huawei_user     TEXT DEFAULT '',
    huawei_pass     TEXT DEFAULT '',
    huawei_station_id TEXT DEFAULT '',

    -- SAJ (elekeeper)
    saj_user        TEXT DEFAULT '',
    saj_pass        TEXT DEFAULT '',
    saj_plant_id    TEXT DEFAULT '',

    -- API genérica (qualquer inversor com endpoint HTTP)
    api_url         TEXT DEFAULT '',
    api_key         TEXT DEFAULT '',
    api_type        TEXT DEFAULT '', -- json_local | modbus | custom

    notes           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Tabela de métricas solares ───────────────────────────────
CREATE TABLE IF NOT EXISTS solar_metrics (
    time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    inverter_id     INTEGER REFERENCES solar_inverters(id) ON DELETE CASCADE,
    client_id       INTEGER REFERENCES clients(id),

    -- Produção
    power_w         FLOAT DEFAULT 0,   -- potência atual em Watts
    energy_today_kwh FLOAT DEFAULT 0,  -- energia gerada hoje kWh
    energy_month_kwh FLOAT DEFAULT 0,  -- energia gerada no mês kWh
    energy_total_kwh FLOAT DEFAULT 0,  -- energia total gerada kWh

    -- Elétrico
    voltage_pv      FLOAT DEFAULT 0,   -- tensão painel solar (V)
    voltage_ac      FLOAT DEFAULT 0,   -- tensão saída AC (V)
    current_ac      FLOAT DEFAULT 0,   -- corrente AC (A)
    frequency_hz    FLOAT DEFAULT 50,  -- frequência (Hz)
    temperature_c   FLOAT DEFAULT 0,   -- temperatura do inversor (°C)

    -- Receita
    revenue_today   FLOAT DEFAULT 0,   -- receita do dia R$
    revenue_month   FLOAT DEFAULT 0,   -- receita do mês R$
    revenue_total   FLOAT DEFAULT 0,   -- receita total R$

    -- Status
    inverter_status TEXT DEFAULT 'unknown', -- generating | idle | offline | fault
    fault_code      TEXT DEFAULT '',
    last_update     TIMESTAMPTZ DEFAULT NOW()
);

-- Transformar em hypertable TimescaleDB
SELECT create_hypertable('solar_metrics', 'time', if_not_exists => TRUE);

-- ── Índices ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_solar_inverters_client ON solar_inverters(client_id);
CREATE INDEX IF NOT EXISTS idx_solar_metrics_inverter ON solar_metrics(inverter_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_solar_metrics_client   ON solar_metrics(client_id, time DESC);

SELECT 'Migration Solar ETI SENTINEL Pro concluída!' as resultado;
