import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartPoint } from "../useLiveReadings";

interface Props {
  title: string;
  points: ChartPoint[];
  dataKey: "bus_voltage_v" | "current_ma";
  unit: string;
  decimals: number;
}

export const formatClock = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function LiveChart({ title, points, dataKey, unit, decimals }: Props) {
  return (
    <div className="card chart-card">
      <h3>{title}</h3>
      {points.length === 0 ? (
        <p className="empty">Waiting for readings…</p>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={formatClock}
              stroke="var(--text-muted)"
              fontSize={12}
            />
            <YAxis
              domain={["auto", "auto"]}
              tickFormatter={(v: number) => v.toFixed(decimals)}
              stroke="var(--text-muted)"
              fontSize={12}
              width={56}
              unit={` ${unit}`}
            />
            <Tooltip
              labelFormatter={(t) => formatClock(Number(t))}
              formatter={(v) => [`${Number(v).toFixed(decimals)} ${unit}`, title]}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            />
            <Line
              dataKey={dataKey}
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
