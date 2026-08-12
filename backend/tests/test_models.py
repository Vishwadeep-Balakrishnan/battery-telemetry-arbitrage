"""Validation of telemetry messages."""

import json

import pytest
from pydantic import ValidationError

from app.models import TelemetryMessage

GOOD = {
    "timestamp": "2026-10-28T17:36:01.123Z",
    "bus_voltage_v": 3.9124,
    "shunt_voltage_mv": 38.21,
    "current_ma": 382.1,
    "power_mw": 1494.0,
    "soc_pct": 97.425,
}


def test_accepts_message_from_telemetry_program():
    msg = TelemetryMessage.model_validate(GOOD)
    assert msg.current_ma == pytest.approx(382.1)
    assert msg.timestamp.utcoffset().total_seconds() == 0


def test_ignores_unknown_fields():
    msg = TelemetryMessage.model_validate({**GOOD, "firmware": "1.2"})
    assert not hasattr(msg, "firmware")


@pytest.mark.parametrize("field", list(GOOD))
def test_rejects_missing_field(field):
    data = {k: v for k, v in GOOD.items() if k != field}
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bus_voltage_v", -1.0),
        ("bus_voltage_v", 40.0),
        ("current_ma", 9000.0),
        ("soc_pct", 101.0),
        ("soc_pct", -0.1),
        ("power_mw", -5.0),
        ("current_ma", "lots"),
    ],
)
def test_rejects_out_of_range(field, value):
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate({**GOOD, field: value})


def test_rejects_nan():
    raw = json.dumps(GOOD).replace("382.1", "NaN")
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(json.loads(raw))


def test_rejects_timestamp_without_timezone():
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate({**GOOD, "timestamp": "2026-10-28T17:36:01"})
