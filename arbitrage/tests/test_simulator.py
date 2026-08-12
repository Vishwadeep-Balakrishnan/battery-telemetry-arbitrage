"""Arbitrage simulator tests. They use the bundled sample CSV and never hit the network."""

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from arbitrage import prices as prices_mod
from arbitrage.battery import Battery, cell_figures_from_readings
from arbitrage.prices import PriceDataError, load_prices
from arbitrage.strategies import lp_upper_bound, summarize, threshold_strategy

START, END = date(2026, 10, 1), date(2026, 10, 7)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if anything tries to reach the PJM API."""
    monkeypatch.delenv("PJM_API_KEY", raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError("tests must not call the network")

    monkeypatch.setattr(prices_mod.requests, "get", blocked)


@pytest.fixture
def sample_prices():
    table, source = load_prices(START, END, "PECO", "da", offline=True)
    assert "SYNTHETIC" in source
    return table


def make_prices(values, start="2026-10-01 00:00") -> pd.DataFrame:
    """A small hand-written price table, one row per hour."""
    local = pd.date_range(start, periods=len(values), freq="h")
    return pd.DataFrame({
        "timestamp": local.tz_localize("America/New_York").tz_convert("UTC"),
        "local_time": local,
        "price": np.asarray(values, dtype=float),
    })


# ---- prices ---------------------------------------------------------------------


def test_sample_covers_one_week_of_hours(sample_prices):
    assert len(sample_prices) == 7 * 24
    assert sample_prices["timestamp"].is_monotonic_increasing
    assert str(sample_prices["timestamp"].dt.tz) == "UTC"
    assert sample_prices["local_time"].dt.date.min() == START
    assert sample_prices["local_time"].dt.date.max() == END


def test_sample_subrange():
    table, _ = load_prices(date(2026, 10, 3), date(2026, 10, 4), "PECO", "rt", offline=True)
    assert len(table) == 48


def test_missing_data_without_key_is_a_clear_error():
    with pytest.raises(PriceDataError, match="PJM_API_KEY"):
        load_prices(date(2025, 1, 1), date(2025, 1, 2), "PECO", "da")


def test_fetch_pjm_parses_and_pages(monkeypatch, tmp_path):
    """The API client with a fake requests.get: paging, headers, column mapping."""
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self._body

    def fake_get(url, params, headers, timeout):
        calls.append((url, dict(params), headers))
        hour = params["startRow"] - 1  # one row per page in this fake
        item = {
            "datetime_beginning_utc": f"2026-10-01T{4 + hour:02d}:00:00",
            "datetime_beginning_ept": f"2026-10-01T{hour:02d}:00:00",
            "pnode_id": 12345,
            "pnode_name": "PECO",
            "total_lmp_da": 20.0 + hour,
        }
        return FakeResponse({"items": [item], "totalRows": 2})

    monkeypatch.setattr(prices_mod, "PAGE_SIZE", 1)
    monkeypatch.setattr(prices_mod.requests, "get", fake_get)
    rows = prices_mod.fetch_pjm(START, START, "PECO", "da", api_key="test-key")

    assert len(calls) == 2
    url, params, headers = calls[0]
    assert url.endswith("/da_hrl_lmps")
    assert headers == {"Ocp-Apim-Subscription-Key": "test-key"}
    assert params["pnode_name"] == "PECO"
    assert params["datetime_beginning_ept"] == "10/01/2026 00:00to10/01/2026 23:59"
    assert list(rows["lmp"]) == [20.0, 21.0]

    table = prices_mod.to_price_table(rows)
    assert table["timestamp"].iloc[0] == pd.Timestamp("2026-10-01T04:00:00", tz="UTC")


# ---- battery model -------------------------------------------------------


def test_battery_validates_parameters():
    with pytest.raises(ValueError):
        Battery(efficiency=1.2)
    with pytest.raises(ValueError):
        Battery(min_soc=0.9, max_soc=0.5)
    battery = Battery(capacity_kwh=10, min_soc=0.1, max_soc=0.9)
    assert battery.usable_kwh == pytest.approx(8.0)
    assert battery.charge_eff * battery.discharge_eff == pytest.approx(battery.efficiency)


# ---- strategies ---------------------------------------------------------------


@pytest.mark.parametrize("market", ["da", "rt"])
@pytest.mark.parametrize("strategy", ["threshold", "lp"])
def test_soc_limits_and_power_respected(market, strategy):
    table, _ = load_prices(START, END, "PECO", market, offline=True)
    battery = Battery()
    if strategy == "threshold":
        results = threshold_strategy(table, battery, k=3)
    else:
        results = lp_upper_bound(table, battery)
    eps = 1e-6
    assert results["soc_kwh"].min() >= battery.min_kwh - eps
    assert results["soc_kwh"].max() <= battery.max_kwh + eps
    assert results["grid_energy_kwh"].abs().max() <= battery.power_kw + eps


def test_threshold_never_beats_lp_bound(sample_prices):
    for k in (1, 2, 3, 4, 6):
        for battery in (Battery(), Battery(capacity_kwh=2, power_kw=0.5, efficiency=0.8)):
            threshold = summarize(threshold_strategy(sample_prices, battery, k), battery)
            lp = summarize(lp_upper_bound(sample_prices, battery), battery)
            assert threshold["total_profit"] <= lp["total_profit"] + 1e-6


def test_sample_week_is_profitable(sample_prices):
    battery = Battery()
    threshold = summarize(threshold_strategy(sample_prices, battery, k=3), battery)
    lp = summarize(lp_upper_bound(sample_prices, battery), battery)
    assert threshold["total_profit"] > 0
    assert threshold["cycles"] > 0
    assert threshold["profit_per_cycle"] == pytest.approx(threshold["total_profit"] / threshold["cycles"])
    # The perfect-foresight bound is meaningfully higher on a peaky week.
    assert lp["total_profit"] > threshold["total_profit"]


def test_efficiency_applied_on_charge_and_discharge():
    # Cheap hour at $10, expensive hour at $100, 81% round trip (90% each way).
    prices = make_prices([10, 100])
    battery = Battery(capacity_kwh=10, power_kw=2, efficiency=0.81, min_soc=0.0, max_soc=1.0)
    results = threshold_strategy(prices, battery, k=1)

    assert list(results["action"]) == ["charge", "discharge"]
    assert results["grid_energy_kwh"].iloc[0] == pytest.approx(2.0)     # bought 2 kWh
    assert results["soc_kwh"].iloc[0] == pytest.approx(1.8)             # stored 2 * 0.9
    assert results["grid_energy_kwh"].iloc[1] == pytest.approx(-1.62)   # sold 1.8 * 0.9
    assert results["soc_kwh"].iloc[1] == pytest.approx(0.0)
    expected = -2.0 * 10 / 1000 + 1.62 * 100 / 1000
    assert results["cash_flow"].sum() == pytest.approx(expected)


def test_lossless_battery_matches_hand_calculation():
    prices = make_prices([10, 100])
    battery = Battery(capacity_kwh=10, power_kw=2, efficiency=1.0, min_soc=0.0, max_soc=1.0)
    lp = lp_upper_bound(prices, battery)
    assert lp["cash_flow"].sum() == pytest.approx(2 * (100 - 10) / 1000)


def test_threshold_skips_days_without_enough_spread():
    # A flat-ish day: the spread is smaller than the round-trip loss.
    prices = make_prices([30 + (h % 2) for h in range(24)])
    results = threshold_strategy(prices, Battery(efficiency=0.85), k=3)
    assert (results["action"] == "idle").all()
    assert results["cash_flow"].sum() == 0


def test_threshold_rejects_bad_k(sample_prices):
    with pytest.raises(ValueError):
        threshold_strategy(sample_prices, Battery(), k=0)
    with pytest.raises(ValueError):
        threshold_strategy(sample_prices, Battery(), k=13)


def test_results_columns(sample_prices):
    results = threshold_strategy(sample_prices, Battery())
    for column in ("timestamp", "price", "action", "grid_energy_kwh", "soc_kwh", "soc_pct", "cash_flow"):
        assert column in results
    assert set(results["action"]) <= {"charge", "discharge", "idle"}


# ---- hardware sizing ------------------------------------------------------------


def test_cell_figures_from_readings():
    readings = pd.DataFrame({
        # rest at 4.00 V, loaded terminal 3.96 V (bus 3.92 V + 40 mV shunt)
        "bus_voltage_v": [4.00, 4.00, 3.92, 3.92, 3.92],
        "shunt_voltage_mv": [0.0, 0.1, 40.0, 40.0, 40.0],
        "current_ma": [0.0, 1.0, 400.0, 400.0, 400.0],
    })
    figures = cell_figures_from_readings(readings)
    assert figures["v_rest"] == pytest.approx(4.0, abs=1e-3)
    assert figures["v_loaded"] == pytest.approx(3.96)
    assert figures["round_trip_efficiency"] == pytest.approx((3.96 / 4.0) ** 2, rel=1e-3)


def test_cell_figures_need_rest_and_load():
    readings = pd.DataFrame({"bus_voltage_v": [3.9], "shunt_voltage_mv": [40.0], "current_ma": [400.0]})
    with pytest.raises(ValueError, match="toggle"):
        cell_figures_from_readings(readings)
