"""Pydantic models: validation of incoming MQTT messages."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TelemetryMessage(BaseModel):
    """One JSON message from the telemetry program on topic battery/telemetry.

    The bounds are the INA219's physical limits with a 0.1 ohm shunt (26 V bus,
    +/-320 mV shunt = +/-3.2 A), with a little margin. Anything outside them
    is a corrupted or foreign message and gets rejected.
    """

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    timestamp: AwareDatetime  # must carry a timezone, e.g. "...Z"
    bus_voltage_v: float = Field(ge=0, le=32.8)
    shunt_voltage_mv: float = Field(ge=-330, le=330)
    current_ma: float = Field(ge=-4000, le=4000)
    power_mw: float = Field(ge=0, le=140_000)
    soc_pct: float = Field(ge=0, le=100)
