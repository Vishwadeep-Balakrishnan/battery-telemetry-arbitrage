// Types and fetch helpers for the backend API.
// All URLs are relative: in dev Vite proxies them, in Docker nginx does.

export interface Reading {
  timestamp: string; // ISO 8601, UTC
  bus_voltage_v: number;
  shunt_voltage_mv: number;
  current_ma: number;
  power_mw: number;
  soc_pct: number;
}

export interface ArbitrageRun {
  id: number;
  created_at: string;
  node: string;
  market: string;
  start_date: string;
  end_date: string;
  battery_source: string;
  capacity_kwh: number;
  power_kw: number;
  efficiency: number;
  k_hours: number;
  threshold_profit: number;
  lp_profit: number;
  cycles: number;
  profit_per_cycle: number;
}

export interface ArbitrageHour {
  timestamp: string;
  price: number;
  action: "charge" | "discharge" | "idle";
  grid_energy_kwh: number;
  soc_kwh: number;
  soc_pct: number;
  cash_flow: number;
}

export interface ArbitrageResult {
  run: ArbitrageRun;
  results: ArbitrageHour[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path}: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

/** Readings from the last `minutes` minutes, oldest first. */
export function fetchRecentReadings(minutes: number): Promise<Reading[]> {
  const start = new Date(Date.now() - minutes * 60_000).toISOString();
  const params = new URLSearchParams({ start, limit: "10000" });
  return getJson<Reading[]>(`/api/readings?${params}`);
}

/** The latest simulator run, or null if none has been stored yet. */
export async function fetchLatestArbitrage(): Promise<ArbitrageResult | null> {
  const response = await fetch("/api/arbitrage/latest");
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`/api/arbitrage/latest: HTTP ${response.status}`);
  }
  return (await response.json()) as ArbitrageResult;
}

/** ws:// or wss:// URL for the live feed on the current host. */
export function liveSocketUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/live`;
}
