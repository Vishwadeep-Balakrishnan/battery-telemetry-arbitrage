"""End-to-end: the CLI on the sample data, writing to a SQLite database that
uses the backend's table definitions, then read back through the backend API code."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert

from app import db as backend_db  # backend/ is on the pytest path
from arbitrage import prices as prices_mod
from arbitrage import run


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.delenv("PJM_API_KEY", raising=False)
    monkeypatch.setattr(prices_mod.requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network in tests")))


@pytest.fixture
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'sim.db'}"
    engine = create_engine(url)
    backend_db.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    return engine


def test_cli_writes_chart_and_database(database, tmp_path, capsys):
    code = run.main(["--start", "2026-10-01", "--end", "2026-10-07", "--node", "PECO",
                     "--offline", "--output-dir", str(tmp_path / "out")])
    assert code == 0
    output = capsys.readouterr().out
    assert "SYNTHETIC" in output
    assert "saved as run 1" in output
    assert (tmp_path / "out" / "arbitrage_PECO_da_2026-10-01_2026-10-07.png").stat().st_size > 10_000

    latest = backend_db.latest_arbitrage(database)
    assert latest["run"]["node"] == "PECO"
    assert latest["run"]["threshold_profit"] <= latest["run"]["lp_profit"] + 1e-9
    assert len(latest["results"]) == 168
    assert latest["results"][0]["timestamp"] == "2026-10-01T04:00:00+00:00"  # midnight EDT


def test_cli_no_db(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = run.main(["--start", "2026-10-02", "--end", "2026-10-03", "--market", "rt",
                     "--offline", "--output-dir", str(tmp_path)])
    assert code == 0
    assert "Database: skipped" in capsys.readouterr().out


def test_cli_unknown_range_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = run.main(["--start", "2025-01-01", "--end", "2025-01-02", "--offline",
                     "--output-dir", str(tmp_path)])
    assert code == 1


def test_cli_hardware_battery_from_readings(database, tmp_path, capsys):
    """--battery hardware sizes the battery from 18650 readings in the database."""
    t0 = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    rows = []
    for i in range(40):
        loaded = (i // 10) % 2 == 1  # load switched on and off every 10 samples
        rows.append({
            "ts": t0 + timedelta(seconds=i / 10),
            "bus_voltage_v": 3.88 if loaded else 4.0,
            "shunt_voltage_mv": 38.0 if loaded else 0.0,
            "current_ma": 380.0 if loaded else 0.0,
            "power_mw": 1474.0 if loaded else 0.0,
            "soc_pct": 99.0,
        })
    with database.begin() as conn:
        conn.execute(insert(backend_db.readings), rows)

    code = run.main(["--start", "2026-10-01", "--end", "2026-10-07", "--offline",
                     "--battery", "hardware", "--cells", "1000", "--output-dir", str(tmp_path)])
    assert code == 0
    output = capsys.readouterr().out
    assert "Measured 18650" in output

    run_row = backend_db.latest_arbitrage(database)["run"]
    assert run_row["battery_source"] == "hardware"
    # 1000 cells x 2.5 Ah x 3.918 V loaded terminal voltage = 9.795 kWh
    assert run_row["capacity_kwh"] == pytest.approx(9.795, rel=1e-3)
    assert run_row["efficiency"] == pytest.approx((3.918 / 4.0) ** 2, rel=1e-3)
