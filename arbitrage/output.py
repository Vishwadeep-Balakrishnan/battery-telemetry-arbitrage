"""Saving simulator results: a matplotlib chart and rows in PostgreSQL."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed (Pi over SSH, CI)
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import Engine, inspect, text

SCHEMA_SQL = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


# ---- Chart ------------------------------------------------------------------


def save_chart(threshold: pd.DataFrame, lp: pd.DataFrame, title: str, path: Path) -> Path:
    """Three stacked panels: prices with actions, SoC, cumulative profit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    t = threshold["local_time"]
    fig, (ax_price, ax_soc, ax_profit) = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    ax_price.plot(t, threshold["price"], color="0.3", linewidth=1.2, label="LMP")
    for action, color in (("charge", "#2a9d8f"), ("discharge", "#e76f51")):
        rows = threshold[threshold["action"] == action]
        ax_price.scatter(rows["local_time"], rows["price"], color=color, s=22, zorder=3, label=action)
    ax_price.set_ylabel("$/MWh")
    ax_price.set_title(title)
    ax_price.legend(loc="upper left", ncol=3, frameon=False)

    ax_soc.plot(t, threshold["soc_pct"], color="#264653", label="threshold")
    ax_soc.plot(t, lp["soc_pct"], color="#e9c46a", linestyle="--", label="perfect foresight (LP)")
    ax_soc.set_ylabel("SoC %")
    ax_soc.set_ylim(0, 100)
    ax_soc.legend(loc="upper left", ncol=2, frameon=False)

    ax_profit.plot(t, threshold["cash_flow"].cumsum(), color="#264653", label="threshold")
    ax_profit.plot(t, lp["cash_flow"].cumsum(), color="#e9c46a", linestyle="--",
                   label="perfect foresight (LP)")
    ax_profit.set_ylabel("cumulative profit $")
    ax_profit.set_xlabel("time (Eastern)")
    ax_profit.legend(loc="upper left", ncol=2, frameon=False)

    for ax in (ax_price, ax_soc, ax_profit):
        ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ---- Database ------------------------------------------------------------------


def ensure_tables(engine: Engine) -> None:
    """Create the tables from db/schema.sql if the backend hasn't yet (Postgres)."""
    if inspect(engine).has_table("arbitrage_runs"):
        return
    if engine.dialect.name != "postgresql":
        raise RuntimeError("arbitrage tables are missing; start the backend once to create them")
    statements = [s.strip() for s in SCHEMA_SQL.read_text().split(";") if s.strip()]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def write_run(engine: Engine, run: dict, results: pd.DataFrame) -> int:
    """Insert one arbitrage_runs row and its hourly arbitrage_results. Returns the run id."""
    ensure_tables(engine)
    columns = ", ".join(run)
    placeholders = ", ".join(f":{name}" for name in run)
    insert_run = text(f"INSERT INTO arbitrage_runs ({columns}) VALUES ({placeholders}) RETURNING id")

    rows = results[["timestamp", "price", "action", "grid_energy_kwh", "soc_kwh", "soc_pct",
                    "cash_flow"]].rename(columns={"timestamp": "ts"})
    with engine.begin() as conn:
        run_id = conn.execute(insert_run, run).scalar_one()
        rows = rows.assign(run_id=run_id)
        records = rows.to_dict(orient="records")
        for record in records:
            record["ts"] = record["ts"].to_pydatetime()
        conn.execute(
            text(
                "INSERT INTO arbitrage_results "
                "(run_id, ts, price, action, grid_energy_kwh, soc_kwh, soc_pct, cash_flow) "
                "VALUES (:run_id, :ts, :price, :action, :grid_energy_kwh, :soc_kwh, :soc_pct, :cash_flow)"
            ),
            records,
        )
    return int(run_id)
