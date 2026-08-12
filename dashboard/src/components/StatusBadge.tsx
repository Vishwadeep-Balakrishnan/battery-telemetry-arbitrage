import { ConnectionStatus } from "../useLiveReadings";

const LABELS: Record<ConnectionStatus, string> = {
  live: "Live",
  "no-data": "Connected, no readings",
  connecting: "Connecting…",
  offline: "Backend offline",
};

// A dot plus a text label, so the state never depends on color alone.
export function StatusBadge({ status }: { status: ConnectionStatus }) {
  return (
    <span className={`status status-${status}`} role="status">
      <span className="status-dot" aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}
