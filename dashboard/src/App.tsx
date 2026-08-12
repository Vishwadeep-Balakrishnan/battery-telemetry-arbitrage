import { useState } from "react";

import { ArbitragePanel } from "./components/ArbitragePanel";
import { LiveChart } from "./components/LiveChart";
import { MetricCard } from "./components/MetricCard";
import { StatusBadge } from "./components/StatusBadge";
import { useLiveReadings } from "./useLiveReadings";

const WINDOW_CHOICES = [1, 5, 15]; // minutes of history in the live charts

export default function App() {
  const [windowMinutes, setWindowMinutes] = useState(5);
  const { points, latest, status } = useLiveReadings(windowMinutes);

  return (
    <main>
      <header className="page-header">
        <h1>Battery Telemetry</h1>
        <StatusBadge status={status} />
      </header>

      <section className="metrics">
        <MetricCard label="Voltage" value={latest?.bus_voltage_v ?? null} unit="V" decimals={3} />
        <MetricCard label="Current" value={latest?.current_ma ?? null} unit="mA" decimals={1} />
        <MetricCard label="Power" value={latest?.power_mw ?? null} unit="mW" decimals={0} />
        <MetricCard label="State of charge" value={latest?.soc_pct ?? null} unit="%" decimals={1} />
      </section>

      <div className="toolbar">
        <label>
          History{" "}
          <select value={windowMinutes} onChange={(e) => setWindowMinutes(Number(e.target.value))}>
            {WINDOW_CHOICES.map((m) => (
              <option key={m} value={m}>
                last {m} min
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="charts">
        <LiveChart title="Bus voltage" points={points} dataKey="bus_voltage_v" unit="V" decimals={2} />
        <LiveChart title="Current" points={points} dataKey="current_ma" unit="mA" decimals={0} />
      </section>

      <ArbitragePanel />
    </main>
  );
}
