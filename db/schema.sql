-- schema.sql - PostgreSQL schema for battery telemetry and arbitrage results.
--
-- Loaded automatically by the postgres container (docker-entrypoint-initdb.d).
-- On a Pi without Docker:  psql -U battery -d battery -f db/schema.sql
-- The backend also creates these tables at startup if they are missing, so
-- running this file by hand is optional. Keep it in sync with backend/app/db.py
-- (a pytest checks that the column names match).

-- One row per INA219 sample received over MQTT.
CREATE TABLE IF NOT EXISTS readings (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ      NOT NULL,  -- sample time from the Pi (UTC)
    bus_voltage_v    DOUBLE PRECISION NOT NULL,  -- load-side voltage (VIN- to GND)
    shunt_voltage_mv DOUBLE PRECISION NOT NULL,  -- drop across the 0.1 ohm shunt
    current_ma       DOUBLE PRECISION NOT NULL,  -- + = discharging into the load
    power_mw         DOUBLE PRECISION NOT NULL,
    soc_pct          DOUBLE PRECISION NOT NULL,  -- coulomb-counted state of charge
    received_at      TIMESTAMPTZ      NOT NULL DEFAULT now()
);

-- Almost every query filters or sorts by sample time.
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings (ts);

-- One row per simulator run (python -m arbitrage.run).
CREATE TABLE IF NOT EXISTS arbitrage_runs (
    id               BIGSERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    node             TEXT             NOT NULL,  -- PJM pricing node / zone, e.g. PECO
    market           TEXT             NOT NULL,  -- 'da' (day-ahead) or 'rt' (real-time)
    start_date       DATE             NOT NULL,
    end_date         DATE             NOT NULL,
    battery_source   TEXT             NOT NULL,  -- 'default' or 'hardware'
    capacity_kwh     DOUBLE PRECISION NOT NULL,
    power_kw         DOUBLE PRECISION NOT NULL,
    efficiency       DOUBLE PRECISION NOT NULL,  -- round-trip, 0..1
    k_hours          INTEGER          NOT NULL,  -- threshold strategy: hours/day to trade
    threshold_profit DOUBLE PRECISION NOT NULL,  -- $
    lp_profit        DOUBLE PRECISION NOT NULL,  -- $, perfect-foresight upper bound
    cycles           DOUBLE PRECISION NOT NULL,  -- equivalent full cycles (threshold)
    profit_per_cycle DOUBLE PRECISION NOT NULL   -- $ per cycle (threshold)
);

-- Hour-by-hour schedule of the threshold strategy for a run.
CREATE TABLE IF NOT EXISTS arbitrage_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT           NOT NULL REFERENCES arbitrage_runs (id) ON DELETE CASCADE,
    ts              TIMESTAMPTZ      NOT NULL,  -- start of the hour (UTC)
    price           DOUBLE PRECISION NOT NULL,  -- LMP, $/MWh
    action          TEXT             NOT NULL,  -- 'charge', 'discharge' or 'idle'
    grid_energy_kwh DOUBLE PRECISION NOT NULL,  -- + bought from grid, - sold to grid
    soc_kwh         DOUBLE PRECISION NOT NULL,  -- energy stored at the end of the hour
    soc_pct         DOUBLE PRECISION NOT NULL,
    cash_flow       DOUBLE PRECISION NOT NULL   -- $, + revenue, - cost
);

CREATE INDEX IF NOT EXISTS idx_arbitrage_results_run ON arbitrage_results (run_id, ts);
