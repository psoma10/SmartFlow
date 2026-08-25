import type { LaneStats, SignalState } from "../lib/types";
import { VehicleIcon } from "./VehicleIcon";

interface Props {
  lane: LaneStats;
  signal: SignalState;
  onTriggerEmergency: (laneId: string) => void;
}

const CONGESTION_LABEL: Record<LaneStats["congestion"], string> = {
  low: "Low",
  medium: "Medium",
  high: "Heavy",
};

export function LaneCard({ lane, signal, onTriggerEmergency }: Props) {
  const light = signal.lane_signals[lane.id] ?? "red";
  const priority = signal.priorities.find((p) => p.lane_id === lane.id);
  const isActive = signal.active_lane === lane.id;
  const greenSeconds = isActive ? Math.ceil(signal.remaining) : null;
  const breakdown = Object.entries(lane.counts).sort(([, a], [, b]) => b - a);

  return (
    <div className={`lane-card congestion-${lane.congestion} ${isActive ? "active" : ""}`}>
      <div className="lane-card-header">
        <span className="lane-name">{lane.name}</span>
        <div className="lane-card-header-right">
          <span className={`signal-dot signal-${light}`} title={`Signal: ${light}`} />
          {!lane.emergency && (
            <button
              className="emergency-icon-btn"
              onClick={() => onTriggerEmergency(lane.id)}
              title="Manually trigger emergency priority for this lane"
              aria-label="Trigger emergency priority"
            >
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor"
                   strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 2v3M10 15v3M2 10h3M15 10h3M4.5 4.5l2 2M13.5 13.5l2 2M15.5 4.5l-2 2M6.5 13.5l-2 2" />
                <circle cx="10" cy="10" r="3.2" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className="lane-metric-row">
        <span className="lane-count">{lane.total}</span>
        <span className="lane-tag">{CONGESTION_LABEL[lane.congestion]}</span>
      </div>

      <div className="lane-countdown">{greenSeconds !== null ? `${greenSeconds}s green` : ""}</div>

      <div className="lane-breakdown">
        {breakdown.map(([label, count]) => (
          <span key={label} className="lane-chip">
            <VehicleIcon type={label} />
            <span className="lane-chip-count">{count}</span>
            <span className="lane-chip-label">{label}</span>
          </span>
        ))}
        {breakdown.length === 0 && <span className="lane-chip empty">no vehicles</span>}
      </div>

      <div className="lane-stats-grid">
        <div>
          <span className="stat-label">Queue</span>
          <span className="stat-value">{lane.stopped}</span>
        </div>
        <div>
          <span className="stat-label">Wait</span>
          <span className="stat-value">{priority ? Math.round(priority.wait_seconds) : 0}s</span>
        </div>
        <div>
          <span className="stat-label">Total seen</span>
          <span className="stat-value">{lane.cumulative}</span>
        </div>
      </div>

      {priority?.starving && <div className="starving-badge">Fairness override pending</div>}

      {lane.emergency && (
        <div className="emergency-detected">Emergency vehicle detected on this lane</div>
      )}
    </div>
  );
}
