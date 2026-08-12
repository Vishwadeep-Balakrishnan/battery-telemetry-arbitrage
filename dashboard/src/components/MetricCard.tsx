interface Props {
  label: string;
  value: number | null;
  unit: string;
  decimals: number;
}

export function MetricCard({ label, value, unit, decimals }: Props) {
  return (
    <div className="card metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value === null ? "—" : value.toFixed(decimals)}
        <span className="metric-unit">{unit}</span>
      </div>
    </div>
  );
}
