"""REST and WebSocket endpoints, fed through the same path MQTT messages take."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import insert

from app import db
from app.mqtt_worker import handle_payload

T0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)


def message(seconds: float, volts=3.9, current=390.0, soc=99.0) -> bytes:
    """A telemetry message `seconds` after T0, as raw MQTT payload bytes."""
    ts = (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    return json.dumps(
        {
            "timestamp": ts,
            "bus_voltage_v": volts,
            "shunt_voltage_mv": current * 0.1,
            "current_ma": current,
            "power_mw": volts * current,
            "soc_pct": soc,
        }
    ).encode()


def test_health(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "database": True, "mqtt_connected": False}


def test_latest_is_404_when_empty(client):
    assert client.get("/api/readings/latest").status_code == 404


def test_bad_payloads_are_not_stored(engine, client):
    assert handle_payload(b"not json", engine) is None
    assert handle_payload(b'{"timestamp": "2026-10-28T12:00:00Z"}', engine) is None
    assert handle_payload(b"\xff\xfe", engine) is None
    assert client.get("/api/readings/latest").status_code == 404


def test_latest_returns_newest(engine, client):
    handle_payload(message(0, volts=3.90), engine)
    handle_payload(message(1, volts=3.80), engine)
    body = client.get("/api/readings/latest").json()
    assert body["bus_voltage_v"] == pytest.approx(3.80)
    assert body["timestamp"].startswith("2026-10-28T12:00:01")


def test_readings_window_and_limit(engine, client):
    for i in range(10):
        handle_payload(message(i, volts=3.0 + i / 10), engine)

    everything = client.get("/api/readings").json()
    assert len(everything) == 10
    assert everything[0]["timestamp"] < everything[-1]["timestamp"]  # oldest first

    window = client.get(
        "/api/readings",
        params={"start": (T0 + timedelta(seconds=2)).isoformat(),
                "end": (T0 + timedelta(seconds=5)).isoformat()},
    ).json()
    assert [r["bus_voltage_v"] for r in window] == pytest.approx([3.2, 3.3, 3.4, 3.5])

    newest_three = client.get("/api/readings", params={"limit": 3}).json()
    assert [r["bus_voltage_v"] for r in newest_three] == pytest.approx([3.7, 3.8, 3.9])


def test_readings_rejects_bad_params(client):
    assert client.get("/api/readings", params={"limit": 0}).status_code == 422
    assert client.get("/api/readings", params={"start": "yesterday"}).status_code == 422
    bad_window = {"start": T0.isoformat(), "end": (T0 - timedelta(hours=1)).isoformat()}
    assert client.get("/api/readings", params=bad_window).status_code == 400


def test_stats(engine, client):
    # 1 W constant for 10 s at 10 Hz -> 10 J = 1/360 Wh
    for i in range(101):
        handle_payload(message(i / 10, volts=4.0, current=250.0), engine)
    handle_payload(message(2.0 + 100, volts=3.0, current=100.0), engine)  # after a gap

    body = client.get(
        "/api/stats",
        params={"start": T0.isoformat(), "end": (T0 + timedelta(minutes=5)).isoformat()},
    ).json()
    assert body["count"] == 102
    assert body["voltage_v"]["min"] == pytest.approx(3.0)
    assert body["voltage_v"]["max"] == pytest.approx(4.0)
    assert body["current_ma"]["max"] == pytest.approx(250.0)
    # The 92 s gap before the last sample is skipped, not integrated.
    assert body["energy_wh"] == pytest.approx(10.0 / 3600.0, rel=1e-6)


def test_stats_empty_window(client):
    body = client.get("/api/stats").json()
    assert body["count"] == 0
    assert body["energy_wh"] == 0.0


def test_energy_wh_trapezoid():
    t = [T0 + timedelta(seconds=s) for s in (0, 1, 2)]
    # 0 -> 3600 mW ramp over 1 s, then flat: 1800 + 3600 mW*s = 5400 mWs = 1.5 mWh
    assert db.energy_wh(list(zip(t, [0.0, 3600.0, 3600.0]))) == pytest.approx(0.0015)
    assert db.energy_wh([]) == 0.0


def test_arbitrage_latest(engine, client):
    assert client.get("/api/arbitrage/latest").status_code == 404

    with engine.begin() as conn:
        run_id = conn.execute(
            insert(db.arbitrage_runs).values(
                node="PECO", market="da", start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 7), battery_source="default", capacity_kwh=13.5,
                power_kw=5.0, efficiency=0.9, k_hours=3, threshold_profit=4.2,
                lp_profit=6.1, cycles=5.5, profit_per_cycle=0.76,
            )
        ).inserted_primary_key[0]
        conn.execute(
            insert(db.arbitrage_results),
            [
                {"run_id": run_id, "ts": T0, "price": 25.0, "action": "charge",
                 "grid_energy_kwh": 5.0, "soc_kwh": 6.1, "soc_pct": 45.0, "cash_flow": -0.125},
                {"run_id": run_id, "ts": T0 + timedelta(hours=1), "price": 80.0,
                 "action": "discharge", "grid_energy_kwh": -5.0, "soc_kwh": 0.8,
                 "soc_pct": 6.0, "cash_flow": 0.4},
            ],
        )

    body = client.get("/api/arbitrage/latest").json()
    assert body["run"]["node"] == "PECO"
    assert body["run"]["lp_profit"] == pytest.approx(6.1)
    assert [r["action"] for r in body["results"]] == ["charge", "discharge"]


def test_websocket_pushes_new_readings(engine, client):
    hub = client.app.state.hub
    with client.websocket_connect("/ws/live") as ws:
        handle_payload(message(0, volts=3.77), engine, on_saved=hub.publish_threadsafe)
        pushed = ws.receive_json()
    assert pushed["bus_voltage_v"] == pytest.approx(3.77)
    assert pushed["timestamp"].startswith("2026-10-28T12:00:00")


def test_cors_header(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "*"
