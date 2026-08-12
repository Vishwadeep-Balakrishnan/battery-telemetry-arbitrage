"""Database tables and queries (SQLAlchemy Core, no ORM).

The table definitions mirror db/schema.sql. They are used to build queries
and, at startup, to create any missing tables (handy on SQLite in tests and
on a fresh Postgres without running schema.sql by hand).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
)

from .models import TelemetryMessage

metadata = MetaData()

# BIGSERIAL on Postgres; SQLite needs INTEGER for autoincrement primary keys.
_Id = BigInteger().with_variant(Integer(), "sqlite")

readings = Table(
    "readings",
    metadata,
    Column("id", _Id, primary_key=True, autoincrement=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("bus_voltage_v", Float, nullable=False),
    Column("shunt_voltage_mv", Float, nullable=False),
    Column("current_ma", Float, nullable=False),
    Column("power_mw", Float, nullable=False),
    Column("soc_pct", Float, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("idx_readings_ts", "ts"),
)

arbitrage_runs = Table(
    "arbitrage_runs",
    metadata,
    Column("id", _Id, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("node", Text, nullable=False),
    Column("market", Text, nullable=False),
    Column("start_date", Date, nullable=False),
    Column("end_date", Date, nullable=False),
    Column("battery_source", Text, nullable=False),
    Column("capacity_kwh", Float, nullable=False),
    Column("power_kw", Float, nullable=False),
    Column("efficiency", Float, nullable=False),
    Column("k_hours", Integer, nullable=False),
    Column("threshold_profit", Float, nullable=False),
    Column("lp_profit", Float, nullable=False),
    Column("cycles", Float, nullable=False),
    Column("profit_per_cycle", Float, nullable=False),
)

arbitrage_results = Table(
    "arbitrage_results",
    metadata,
    Column("id", _Id, primary_key=True, autoincrement=True),
    Column("run_id", _Id, ForeignKey("arbitrage_runs.id", ondelete="CASCADE"), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("price", Float, nullable=False),
    Column("action", Text, nullable=False),
    Column("grid_energy_kwh", Float, nullable=False),
    Column("soc_kwh", Float, nullable=False),
    Column("soc_pct", Float, nullable=False),
    Column("cash_flow", Float, nullable=False),
    Index("idx_arbitrage_results_run", "run_id", "ts"),
)

READING_FIELDS = ("bus_voltage_v", "shunt_voltage_mv", "current_ma", "power_mw", "soc_pct")

# Gaps longer than this (telemetry stopped, Pi rebooted) are not integrated
# into energy totals.
MAX_ENERGY_GAP_S = 5.0


def make_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    metadata.create_all(engine)  # only creates tables that are missing
    return engine


def as_utc(ts: datetime) -> datetime:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def reading_to_dict(row) -> dict:
    data = {"timestamp": as_utc(row.ts).isoformat()}
    for name in READING_FIELDS:
        data[name] = getattr(row, name)
    return data


# ---- readings -------------------------------------------------------------


def insert_reading(engine: Engine, msg: TelemetryMessage) -> None:
    values = {name: getattr(msg, name) for name in READING_FIELDS}
    values["ts"] = as_utc(msg.timestamp)
    with engine.begin() as conn:
        conn.execute(insert(readings).values(**values))


def latest_reading(engine: Engine) -> dict | None:
    query = select(readings).order_by(readings.c.ts.desc()).limit(1)
    with engine.connect() as conn:
        row = conn.execute(query).first()
    return reading_to_dict(row) if row else None


def readings_between(
    engine: Engine, start: datetime | None, end: datetime | None, limit: int
) -> list[dict]:
    """The newest `limit` readings in [start, end], returned oldest first."""
    query = select(readings)
    if start is not None:
        query = query.where(readings.c.ts >= as_utc(start))
    if end is not None:
        query = query.where(readings.c.ts <= as_utc(end))
    query = query.order_by(readings.c.ts.desc()).limit(limit)
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    return [reading_to_dict(row) for row in reversed(rows)]


def energy_wh(samples: list[tuple[datetime, float]]) -> float:
    """Integrate power (mW) over time with the trapezoid rule -> watt-hours.

    `samples` are (timestamp, power_mw) sorted by time. Gaps longer than
    MAX_ENERGY_GAP_S are skipped rather than bridged.
    """
    total_mws = 0.0  # milliwatt-seconds
    for (t0, p0), (t1, p1) in zip(samples, samples[1:]):
        dt = (as_utc(t1) - as_utc(t0)).total_seconds()
        if 0 < dt <= MAX_ENERGY_GAP_S:
            total_mws += (p0 + p1) / 2.0 * dt
    return total_mws / 1000.0 / 3600.0


def reading_stats(engine: Engine, start: datetime, end: datetime) -> dict:
    window = (readings.c.ts >= as_utc(start)) & (readings.c.ts <= as_utc(end))
    summary = select(
        func.count().label("count"),
        func.min(readings.c.bus_voltage_v).label("v_min"),
        func.max(readings.c.bus_voltage_v).label("v_max"),
        func.avg(readings.c.bus_voltage_v).label("v_avg"),
        func.min(readings.c.current_ma).label("i_min"),
        func.max(readings.c.current_ma).label("i_max"),
        func.avg(readings.c.current_ma).label("i_avg"),
    ).where(window)
    power = select(readings.c.ts, readings.c.power_mw).where(window).order_by(readings.c.ts)

    with engine.connect() as conn:
        s = conn.execute(summary).one()
        samples = [(row.ts, row.power_mw) for row in conn.execute(power)]

    return {
        "start": as_utc(start).isoformat(),
        "end": as_utc(end).isoformat(),
        "count": s.count,
        "voltage_v": {"min": s.v_min, "max": s.v_max, "avg": s.v_avg},
        "current_ma": {"min": s.i_min, "max": s.i_max, "avg": s.i_avg},
        "energy_wh": energy_wh(samples),
    }


# ---- arbitrage ------------------------------------------------------------


def latest_arbitrage(engine: Engine) -> dict | None:
    run_query = select(arbitrage_runs).order_by(arbitrage_runs.c.id.desc()).limit(1)
    with engine.connect() as conn:
        run = conn.execute(run_query).first()
        if run is None:
            return None
        result_query = (
            select(arbitrage_results)
            .where(arbitrage_results.c.run_id == run.id)
            .order_by(arbitrage_results.c.ts)
        )
        results = conn.execute(result_query).all()

    run_dict = dict(run._mapping)
    run_dict["created_at"] = as_utc(run.created_at).isoformat()
    run_dict["start_date"] = run.start_date.isoformat()
    run_dict["end_date"] = run.end_date.isoformat()
    return {
        "run": run_dict,
        "results": [
            {
                "timestamp": as_utc(r.ts).isoformat(),
                "price": r.price,
                "action": r.action,
                "grid_energy_kwh": r.grid_energy_kwh,
                "soc_kwh": r.soc_kwh,
                "soc_pct": r.soc_pct,
                "cash_flow": r.cash_flow,
            }
            for r in results
        ],
    }
