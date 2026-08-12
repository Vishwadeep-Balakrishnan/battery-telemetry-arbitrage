"""Two ways to run the battery against a price series.

threshold_strategy  - realistic and simple: each day, charge in the k cheapest
                      hours and discharge in the k most expensive hours.
lp_upper_bound      - perfect foresight: a linear program that knows every
                      price in advance. No real strategy can beat it, so it is
                      the yardstick for the threshold strategy.

Both return the same results table:
  timestamp, price, action, grid_energy_kwh, soc_kwh, soc_pct, cash_flow
"""

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import diags, hstack, identity

from .battery import Battery

# Energy flows smaller than this (kWh) are treated as zero when labelling actions.
TOLERANCE_KWH = 1e-6


def build_results(prices: pd.DataFrame, grid_kwh: np.ndarray, soc_kwh: np.ndarray,
                  battery: Battery) -> pd.DataFrame:
    """Assemble the results table from hourly grid energy and end-of-hour SoC."""
    action = np.where(grid_kwh > TOLERANCE_KWH, "charge",
                      np.where(grid_kwh < -TOLERANCE_KWH, "discharge", "idle"))
    return pd.DataFrame(
        {
            "timestamp": prices["timestamp"].values,
            "local_time": prices["local_time"].values,
            "price": prices["price"].values,
            "action": action,
            "grid_energy_kwh": grid_kwh,
            "soc_kwh": soc_kwh,
            "soc_pct": soc_kwh / battery.capacity_kwh * 100.0,
            # $/MWh -> $/kWh is /1000. Buying costs money, selling earns it.
            "cash_flow": -grid_kwh * prices["price"].values / 1000.0,
        }
    )


# ---- (a) daily threshold strategy ------------------------------------------


def plan_threshold_actions(prices: pd.DataFrame, battery: Battery, k: int) -> pd.Series:
    """Label each hour 'charge', 'discharge' or 'idle' for the threshold strategy."""
    plan = pd.Series("idle", index=prices.index)
    for _, day in prices.groupby(prices["local_time"].dt.date):
        cheap = day.nsmallest(k, "price")
        expensive = day.drop(cheap.index).nlargest(k, "price")
        # Skip days where the spread doesn't even cover the round-trip loss.
        if expensive["price"].mean() * battery.efficiency <= cheap["price"].mean():
            continue
        plan[cheap.index] = "charge"
        plan[expensive.index] = "discharge"
    return plan


def threshold_strategy(prices: pd.DataFrame, battery: Battery, k: int = 3) -> pd.DataFrame:
    """Charge in the k cheapest hours of each day, discharge in the k dearest.

    Each hour moves at most power_kw, limited by the SoC window. Hours are
    played in order, so an expensive hour that comes before the day's cheap
    hours finds less energy to sell; that is part of why this strategy falls
    short of the perfect-foresight bound.
    """
    if not 1 <= k <= 12:
        raise ValueError("k must be between 1 and 12 hours")
    plan = plan_threshold_actions(prices, battery, k)

    soc = battery.min_kwh  # start (and ideally end) empty
    grid = np.zeros(len(prices))
    soc_trace = np.zeros(len(prices))
    for i, action in enumerate(plan):
        if action == "charge":
            room = battery.max_kwh - soc
            bought = min(battery.power_kw, room / battery.charge_eff)
            soc += bought * battery.charge_eff
            grid[i] = bought
        elif action == "discharge":
            available = soc - battery.min_kwh
            sold = min(battery.power_kw, available * battery.discharge_eff)
            soc -= sold / battery.discharge_eff
            grid[i] = -sold
        soc_trace[i] = soc
    return build_results(prices, grid, soc_trace, battery)


# ---- (b) perfect-foresight linear program ----------------------------------


def lp_upper_bound(prices: pd.DataFrame, battery: Battery) -> pd.DataFrame:
    """Best possible schedule with every price known in advance.

    Variables, for each hour t of T:
      c[t]  energy bought from the grid (kWh), 0 <= c <= power_kw
      d[t]  energy sold to the grid (kWh),     0 <= d <= power_kw
      s[t]  energy stored at the end of hour t, min_kwh <= s <= max_kwh
    Maximise  sum(price[t] * (d[t] - c[t])) / 1000
    subject to s[t] = s[t-1] + charge_eff * c[t] - d[t] / discharge_eff,
               s[-1] = min_kwh (same starting point as the threshold strategy).
    """
    n = len(prices)
    price = prices["price"].to_numpy()

    # linprog minimises, so minimise cost = price * (c - d).
    objective = np.concatenate([price, -price, np.zeros(n)]) / 1000.0

    # Equality rows: -charge_eff*c[t] + d[t]/discharge_eff + s[t] - s[t-1] = 0
    store = identity(n, format="csr") - diags([1.0], [-1], shape=(n, n), format="csr")
    a_eq = hstack([
        -battery.charge_eff * identity(n, format="csr"),
        (1.0 / battery.discharge_eff) * identity(n, format="csr"),
        store,
    ], format="csr")
    b_eq = np.zeros(n)
    b_eq[0] = battery.min_kwh  # s[-1] moves to the right-hand side

    bounds = ([(0, battery.power_kw)] * (2 * n)
              + [(battery.min_kwh, battery.max_kwh)] * n)
    solution = linprog(objective, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not solution.success:
        raise RuntimeError(f"LP failed: {solution.message}")

    charge, discharge, soc = np.split(solution.x, 3)
    return build_results(prices, charge - discharge, soc, battery)


# ---- Summary ----------------------------------------------------------------


def summarize(results: pd.DataFrame, battery: Battery) -> dict:
    """Total profit, equivalent full cycles, and profit per cycle."""
    sold_kwh = -results.loc[results["grid_energy_kwh"] < 0, "grid_energy_kwh"].sum()
    # Energy that left the cells (before discharge losses), in full-window cycles.
    cycles = sold_kwh / battery.discharge_eff / battery.usable_kwh
    profit = float(results["cash_flow"].sum())
    return {
        "total_profit": profit,
        "cycles": float(cycles),
        "profit_per_cycle": profit / cycles if cycles > 0 else 0.0,
        "energy_bought_kwh": float(results.loc[results["grid_energy_kwh"] > 0, "grid_energy_kwh"].sum()),
        "energy_sold_kwh": float(sold_kwh),
    }
