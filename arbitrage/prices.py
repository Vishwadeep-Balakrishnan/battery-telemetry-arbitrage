"""Hourly LMPs from PJM Data Miner 2, with a CSV cache and an offline sample.

API notes (checked against PJM's Data Miner 2 API guide, see README):
  * base URL  https://api.pjm.com/api/v1/<feed>
  * feeds     da_hrl_lmps (day-ahead hourly), rt_hrl_lmps (real-time hourly)
  * auth      header Ocp-Apim-Subscription-Key: <your key>   (env PJM_API_KEY)
  * paging    rowCount (max 50000) + startRow (1-based), totalRows in the reply
  * prices    total_lmp_da / total_lmp_rt in $/MWh

Every price table this module returns has the columns:
  timestamp   start of the hour, tz-aware UTC
  local_time  start of the hour, naive Eastern Prevailing Time (for daily grouping)
  price       LMP in $/MWh
"""

import os
from datetime import date
from pathlib import Path

import pandas as pd
import requests

API_BASE = "https://api.pjm.com/api/v1"
FEEDS = {"da": "da_hrl_lmps", "rt": "rt_hrl_lmps"}
PAGE_SIZE = 50_000

DATA_DIR = Path(__file__).resolve().parent / "data"
SAMPLE_CSV = DATA_DIR / "sample_prices_synthetic.csv"
CACHE_DIR = DATA_DIR / "cache"

# Columns of the cached / sample CSV files.
CSV_COLUMNS = ["datetime_beginning_utc", "datetime_beginning_ept", "pnode_name", "market", "lmp"]


class PriceDataError(RuntimeError):
    pass


# ---- PJM API ----------------------------------------------------------------


def fetch_pjm(
    start: date, end: date, node: str, market: str, api_key: str, pnode_id: int | None = None
) -> pd.DataFrame:
    """Download hourly LMPs for [start, end] (whole days, EPT). Returns CSV-shaped rows."""
    price_field = f"total_lmp_{market}"
    params = {
        "rowCount": PAGE_SIZE,
        "startRow": 1,
        "datetime_beginning_ept": f"{start:%m/%d/%Y} 00:00to{end:%m/%d/%Y} 23:59",
        "row_is_current": "TRUE",
        "fields": f"datetime_beginning_utc;datetime_beginning_ept;pnode_id;pnode_name;{price_field}",
    }
    if pnode_id is not None:
        params["pnode_id"] = pnode_id
    else:
        params["pnode_name"] = node

    items = []
    while True:
        response = requests.get(
            f"{API_BASE}/{FEEDS[market]}",
            params=params,
            headers={"Ocp-Apim-Subscription-Key": api_key},
            timeout=60,
        )
        if response.status_code in (401, 403):
            raise PriceDataError("PJM rejected the API key (check PJM_API_KEY)")
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise PriceDataError(f"PJM API error: {body['errors']}")

        page = body.get("items", [])
        items.extend(page)
        total = body.get("totalRows", body.get("TotalRows", len(items)))
        if not page or len(items) >= total:
            break
        params["startRow"] += PAGE_SIZE

    if not items:
        raise PriceDataError(f"PJM returned no rows for {node} {market} {start}..{end}")

    raw = pd.DataFrame(items)
    return pd.DataFrame(
        {
            "datetime_beginning_utc": raw["datetime_beginning_utc"],
            "datetime_beginning_ept": raw["datetime_beginning_ept"],
            "pnode_name": raw["pnode_name"],
            "market": market,
            "lmp": raw[price_field].astype(float),
        }
    )


# ---- CSV helpers ---------------------------------------------------------------


def to_price_table(rows: pd.DataFrame) -> pd.DataFrame:
    """CSV-shaped rows -> the standard (timestamp, local_time, price) table."""
    table = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(rows["datetime_beginning_utc"]).dt.tz_localize("UTC"),
            "local_time": pd.to_datetime(rows["datetime_beginning_ept"]),
            "price": rows["lmp"].astype(float),
        }
    )
    # A node name can match more than one pnode; keep one price per hour.
    table = table.drop_duplicates(subset="timestamp").sort_values("timestamp")
    return table.reset_index(drop=True)


def select_days(table: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    days = table["local_time"].dt.date
    return table[(days >= start) & (days <= end)].reset_index(drop=True)


def cache_path(start: date, end: date, node: str, market: str) -> Path:
    return CACHE_DIR / f"{market}_{node}_{start}_{end}.csv"


def load_sample(start: date, end: date, node: str, market: str) -> pd.DataFrame | None:
    """Sample prices for the request, or None if the sample doesn't cover it."""
    rows = pd.read_csv(SAMPLE_CSV)
    rows = rows[(rows["pnode_name"] == node) & (rows["market"] == market)]
    if rows.empty:
        return None
    table = select_days(to_price_table(rows), start, end)
    expected_days = (end - start).days + 1
    if table["local_time"].dt.date.nunique() < expected_days:
        return None
    return table


# ---- Main entry point --------------------------------------------------------------


def load_prices(
    start: date,
    end: date,
    node: str = "PECO",
    market: str = "da",
    offline: bool = False,
    pnode_id: int | None = None,
) -> tuple[pd.DataFrame, str]:
    """Hourly prices for [start, end]. Returns (table, description of the source).

    Order: cached CSV -> PJM API (if PJM_API_KEY is set and not offline)
    -> bundled synthetic sample.
    """
    if market not in FEEDS:
        raise ValueError(f"market must be one of {sorted(FEEDS)}")
    if end < start:
        raise ValueError("end date is before start date")

    cached = cache_path(start, end, node, market)
    if cached.exists():
        return to_price_table(pd.read_csv(cached)), f"cache ({cached.name})"

    api_key = os.environ.get("PJM_API_KEY", "").strip()
    if api_key and not offline:
        rows = fetch_pjm(start, end, node, market, api_key, pnode_id)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        rows[CSV_COLUMNS].to_csv(cached, index=False)
        return select_days(to_price_table(rows), start, end), "PJM Data Miner 2 API"

    sample = load_sample(start, end, node, market)
    if sample is not None:
        return sample, "bundled SYNTHETIC sample (set PJM_API_KEY for real prices)"

    raise PriceDataError(
        f"no prices for {node} {market} {start}..{end}: set PJM_API_KEY to download "
        "them, or use the sample range 2026-10-01..2026-10-07 for PECO"
    )
