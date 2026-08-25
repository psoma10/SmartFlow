import type { LaneStats, SignalState } from "../lib/types";

interface Props {
  lanes: LaneStats[];
  signal: SignalState;
}

/** Headline fleet-level counters — the numbers a traffic engineer glances at
 * first, before drilling into any one lane. */
export function StatStrip({ lanes, signal }: Props) {
  const total = lanes.reduce((sum, l) => sum + l.total, 0);
  const congested = lanes.filter((l) => l.congestion !== "low").length;
  const seen = lanes.reduce((sum, l) => sum + l.cumulative, 0);
  const avgWait = signal.priorities.length
    ? Math.round(signal.priorities.reduce((sum, p) => sum + p.wait_seconds, 0) / signal.priorities.length)
    : 0;

  return (
    <div className="stat-strip">
      <div className="stat-tile">
        <span className="stat-tile-value">{total}</span>
        <span className="stat-tile-label">Vehicles now</span>
      </div>
      <div className={`stat-tile ${congested > 0 ? "warn" : ""}`}>
        <span className="stat-tile-value">{congested}</span>
        <span className="stat-tile-label">Lanes congested</span>
      </div>
      <div className="stat-tile">
        <span className="stat-tile-value">{avgWait}s</span>
        <span className="stat-tile-label">Avg. wait</span>
      </div>
      <div className="stat-tile">
        <span className="stat-tile-value">{seen}</span>
        <span className="stat-tile-label">Total seen</span>
      </div>
    </div>
  );
}
