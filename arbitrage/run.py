"""Command-line entry point.

    python -m arbitrage.run --start 2026-10-01 --end 2026-10-07 --node PECO

Loads hourly PJM prices, runs the threshold strategy and the perfect-foresight
LP, prints a summary, saves a chart, and (if DATABASE_URL is set) stores the
run for the dashboard.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine

from .battery import Battery, battery_from_hardware
from .output import save_chart, write_run
from .prices import PriceDataError, load_prices
from .strategies import lp_upper_bound, summarize, threshold_strategy

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output"


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Battery arbitrage on PJM hourly LMPs")
    p.add_argument("--start", type=date.fromisoformat, required=True, help="first day, YYYY-MM-DD (EPT)")
    p.add_argument("--end", type=date.fromisoformat, required=True, help="last day, YYYY-MM-DD (EPT)")
    p.add_argument("--node", default="PECO", help="PJM pnode name, e.g. a zone like PECO (default)")
    p.add_argument("--pnode-id", type=int, help="filter by numeric pnode_id instead of the name")
    p.add_argument("--market", choices=["da", "rt"], default="da", help="day-ahead or real-time (default da)")
    p.add_argument("--k", type=int, default=3, help="threshold strategy: hours to charge/discharge per day")
    p.add_argument("--offline", action="store_true", help="never call the PJM API")

    b = p.add_argument_group("battery (default: 13.5 kWh / 5 kW home battery)")
    b.add_argument("--battery", choices=["default", "hardware"], default="default",
                   help="'hardware' sizes the battery from the 18650 readings in the database")
    b.add_argument("--capacity-kwh", type=float, default=13.5)
    b.add_argument("--power-kw", type=float, default=5.0)
    b.add_argument("--efficiency", type=float, default=0.90, help="round trip, 0..1")
    b.add_argument("--min-soc", type=float, default=0.10)
    b.add_argument("--max-soc", type=float, default=0.95)
    b.add_argument("--cells", type=int, default=1, help="hardware mode: scale the cell up to N cells")
    b.add_argument("--rated-mah", type=float, default=2500.0, help="hardware mode: cell's rated capacity")
    b.add_argument("--c-rate", type=float, default=0.5, help="hardware mode: power = capacity x C-rate")

    p.add_argument("--no-db", action="store_true", help="don't write results to PostgreSQL")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="where to save the chart")
    return p.parse_args(argv)


def make_battery(args, database_url: str | None) -> tuple[Battery, str]:
    if args.battery == "default":
        battery = Battery(args.capacity_kwh, args.power_kw, args.efficiency, args.min_soc, args.max_soc)
        return battery, "default"

    if not database_url:
        sys.exit("--battery hardware needs DATABASE_URL to read the telemetry readings")
    battery, figures = battery_from_hardware(
        create_engine(database_url), args.cells, args.rated_mah, args.c_rate
    )
    print(f"Measured 18650 from {figures['samples']} readings: "
          f"rest {figures['v_rest']:.3f} V, loaded {figures['v_loaded']:.3f} V "
          f"at {figures['avg_loaded_current_ma']:.0f} mA -> round trip ~{figures['round_trip_efficiency']:.1%}")
    return battery, "hardware"


def main(argv=None) -> int:
    args = parse_args(argv)
    database_url = os.environ.get("DATABASE_URL")

    battery, source = make_battery(args, database_url)
    try:
        prices, price_source = load_prices(args.start, args.end, args.node, args.market,
                                           args.offline, args.pnode_id)
    except PriceDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    threshold = threshold_strategy(prices, battery, args.k)
    lp = lp_upper_bound(prices, battery)
    summary = summarize(threshold, battery)
    lp_summary = summarize(lp, battery)

    print(f"Prices:  {len(prices)} hours of {args.market.upper()} LMP at {args.node} from {price_source}")
    print(f"Battery: {battery.capacity_kwh:.6g} kWh, {battery.power_kw:.6g} kW, "
          f"{battery.efficiency:.0%} round trip, SoC {battery.min_soc:.0%}-{battery.max_soc:.0%} ({source})")
    print(f"Threshold (k={args.k}): profit ${summary['total_profit']:.4f}, "
          f"{summary['cycles']:.2f} cycles, ${summary['profit_per_cycle']:.4f}/cycle")
    print(f"Perfect foresight LP: profit ${lp_summary['total_profit']:.4f}, "
          f"{lp_summary['cycles']:.2f} cycles")
    if lp_summary["total_profit"] > 0:
        print(f"Threshold captures {summary['total_profit'] / lp_summary['total_profit']:.0%} of the LP bound")

    chart = save_chart(
        threshold, lp,
        f"{args.node} {args.market.upper()} LMP, {args.start} to {args.end}",
        args.output_dir / f"arbitrage_{args.node}_{args.market}_{args.start}_{args.end}.png",
    )
    print(f"Chart:   {chart}")

    if args.no_db or not database_url:
        print("Database: skipped (set DATABASE_URL to show this run on the dashboard)")
        return 0

    run = {
        "node": args.node, "market": args.market,
        "start_date": args.start, "end_date": args.end,
        "battery_source": source, "capacity_kwh": battery.capacity_kwh,
        "power_kw": battery.power_kw, "efficiency": battery.efficiency, "k_hours": args.k,
        "threshold_profit": summary["total_profit"], "lp_profit": lp_summary["total_profit"],
        "cycles": summary["cycles"], "profit_per_cycle": summary["profit_per_cycle"],
    }
    run_id = write_run(create_engine(database_url), run, threshold)
    print(f"Database: saved as run {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
