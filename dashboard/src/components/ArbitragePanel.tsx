import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ArbitrageResult, fetchLatestArbitrage } from "../api";

// PJM prices are in Eastern time, so the chart is too.
const formatEastern = (ms: number) =>
  new Date(ms).toLocaleString([], {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "2-digit",
  });

const money = (x: number) => (Math.abs(x) < 1 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`);

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="metric-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

export function ArbitragePanel() {
  const [data, setData] = useState<ArbitrageResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchLatestArbitrage()
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const header = (
    <div className="panel-header">
      <h2>Power market arbitrage</h2>
      <button onClick={load} disabled={loading}>
        {loading ? "Loading…" : "Refresh"}
      </button>
    </div>
  );

  if (error) {
    return <section className="card">{header}<p className="empty">Could not load results: {error}</p></section>;
  }
  if (!data) {
    return (
      <section className="card">
        {header}
        <p className="empty">
          No simulator runs yet. Run <code>python -m arbitrage.run --start 2026-10-01 --end 2026-10-07 --node PECO</code>{" "}
          with <code>DATABASE_URL</code> set, then refresh.
        </p>
      </section>
    );
  }

  const { run, results } = data;
  const hours = results.map((h) => ({ ...h, t: Date.parse(h.timestamp) }));
  const charges = hours.filter((h) => h.action === "charge");
  const discharges = hours.filter((h) => h.action === "discharge");
  const capture = run.lp_profit > 0 ? `${((run.threshold_profit / run.lp_profit) * 100).toFixed(0)}%` : "—";
  const xAxis = (
    <XAxis
      dataKey="t"
      type="number"
      scale="time"
      domain={["dataMin", "dataMax"]}
      tickFormatter={formatEastern}
      stroke="var(--text-muted)"
      fontSize={12}
      minTickGap={40}
    />
  );
  const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--border)" };

  return (
    <section className="card">
      {header}
      <p className="subtle">
        {run.node} {run.market === "da" ? "day-ahead" : "real-time"} LMP, {run.start_date} to {run.end_date} ·{" "}
        {run.capacity_kwh.toPrecision(3)} kWh / {run.power_kw.toPrecision(3)} kW battery,{" "}
        {(run.efficiency * 100).toFixed(0)}% round trip ({run.battery_source}) · threshold strategy, k = {run.k_hours} h
      </p>

      <div className="stats-row">
        <Stat label="Simulated profit" value={money(run.threshold_profit)} />
        <Stat label="Perfect-foresight bound" value={money(run.lp_profit)} />
        <Stat label="Share of bound" value={capture} />
        <Stat label="Cycles" value={run.cycles.toFixed(2)} />
        <Stat label="Profit per cycle" value={money(run.profit_per_cycle)} />
      </div>

      <h3>Price and actions</h3>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={hours} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          {xAxis}
          <YAxis stroke="var(--text-muted)" fontSize={12} width={56} unit=" $" />
          <Tooltip
            labelFormatter={(t) => formatEastern(Number(t))}
            formatter={(v, name) => [`$${Number(v).toFixed(2)}/MWh`, name]}
            contentStyle={tooltipStyle}
          />
          <Legend />
          <Line name="LMP" dataKey="price" stroke="var(--text-secondary)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Scatter name="Charge" data={charges} dataKey="price" fill="var(--charge)" isAnimationActive={false} />
          <Scatter name="Discharge" data={discharges} dataKey="price" fill="var(--discharge)" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>

      <h3>Battery state of charge</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={hours} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          {xAxis}
          <YAxis domain={[0, 100]} stroke="var(--text-muted)" fontSize={12} width={56} unit=" %" />
          <Tooltip
            labelFormatter={(t) => formatEastern(Number(t))}
            formatter={(v) => [`${Number(v).toFixed(1)} %`, "SoC"]}
            contentStyle={tooltipStyle}
          />
          <Line dataKey="soc_pct" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}
