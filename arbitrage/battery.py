"""Battery model, and an option to size it from the physical 18650 cell.

Conventions used everywhere in the simulator:
  * one row of prices = one hour, so power (kW) x 1 h = energy (kWh)
  * round-trip efficiency is split evenly: charge_eff = discharge_eff = sqrt(rte)
  * energy bought from the grid is positive, energy sold is negative
"""

import math
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Engine, text


@dataclass
class Battery:
    # Defaults: a typical home battery (13.5 kWh, 5 kW continuous, 90% round trip).
    capacity_kwh: float = 13.5
    power_kw: float = 5.0
    efficiency: float = 0.90  # round trip, 0..1
    min_soc: float = 0.10     # fraction of capacity kept in reserve
    max_soc: float = 0.95     # fraction of capacity never exceeded

    def __post_init__(self):
        if self.capacity_kwh <= 0 or self.power_kw <= 0:
            raise ValueError("capacity and power must be positive")
        if not 0 < self.efficiency <= 1:
            raise ValueError("efficiency must be in (0, 1]")
        if not 0 <= self.min_soc < self.max_soc <= 1:
            raise ValueError("need 0 <= min_soc < max_soc <= 1")

    @property
    def charge_eff(self) -> float:
        return math.sqrt(self.efficiency)

    @property
    def discharge_eff(self) -> float:
        return math.sqrt(self.efficiency)

    @property
    def min_kwh(self) -> float:
        return self.capacity_kwh * self.min_soc

    @property
    def max_kwh(self) -> float:
        return self.capacity_kwh * self.max_soc

    @property
    def usable_kwh(self) -> float:
        return self.max_kwh - self.min_kwh


# ---- Sizing from the hardware ---------------------------------------------
#
# The INA219 sits between the cell and the load, so the database holds the
# cell's discharge behaviour. Two figures come out of it:
#
#   capacity:   rated Ah x average terminal voltage under load
#   efficiency: the cell's terminal voltage sags under load because of its
#               internal resistance. Discharge efficiency ~ V_loaded / V_rest,
#               and assuming charging loses about the same, round trip is that
#               squared. (Charge current never passes the sensor in this
#               wiring, so it cannot be measured directly.)
#
# Record a session first where the load switch is toggled on and off a few
# times so both rest and loaded samples exist.

REST_MAX_MA = 5.0     # |current| below this counts as "at rest"
LOADED_MIN_MA = 50.0  # current above this counts as "under load"


def cell_figures_from_readings(readings: pd.DataFrame) -> dict:
    """Estimate per-cell voltage and efficiency from telemetry readings.

    `readings` needs columns bus_voltage_v, shunt_voltage_mv and current_ma.
    """
    # Terminal voltage of the cell = load-side voltage + drop across the shunt.
    terminal_v = readings["bus_voltage_v"] + readings["shunt_voltage_mv"] / 1000.0
    rest = terminal_v[readings["current_ma"].abs() < REST_MAX_MA]
    loaded = terminal_v[readings["current_ma"] > LOADED_MIN_MA]
    if rest.empty or loaded.empty:
        raise ValueError(
            "need readings both at rest and under load; toggle the load switch "
            "on and off a few times while the telemetry program runs"
        )

    v_rest = float(rest.median())
    v_loaded = float(loaded.median())
    discharge_eff = v_loaded / v_rest
    round_trip = min(max(discharge_eff**2, 0.5), 0.99)  # keep it physically sensible
    return {
        "v_rest": v_rest,
        "v_loaded": v_loaded,
        "avg_loaded_current_ma": float(readings.loc[readings["current_ma"] > LOADED_MIN_MA, "current_ma"].mean()),
        "round_trip_efficiency": round_trip,
        "samples": len(readings),
    }


def load_readings(engine: Engine) -> pd.DataFrame:
    query = text("SELECT bus_voltage_v, shunt_voltage_mv, current_ma FROM readings")
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def battery_from_hardware(
    engine: Engine, cells: int = 1, rated_mah: float = 2500.0, c_rate: float = 0.5
) -> tuple[Battery, dict]:
    """Size a battery from the measured 18650, scaled up to `cells` cells.

    Power is capacity x c_rate (0.5C is a gentle rate for 18650s).
    Returns the Battery and the measured figures, for printing.
    """
    figures = cell_figures_from_readings(load_readings(engine))
    cell_kwh = rated_mah / 1000.0 * figures["v_loaded"] / 1000.0
    capacity_kwh = cell_kwh * cells
    battery = Battery(
        capacity_kwh=capacity_kwh,
        power_kw=capacity_kwh * c_rate,
        efficiency=figures["round_trip_efficiency"],
    )
    return battery, figures
