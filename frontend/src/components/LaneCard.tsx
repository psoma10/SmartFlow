import type { LaneStats, SignalState } from "../lib/types";

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

  return (
    <div className={`lane-card congestion-${lane.congestion} ${isActive ? "active" : ""}`}>
      <div className="lane-card-header">
        <span className="lane-name">{lane.name}</span>
        <span className={`signal-dot signal-${light}`} title={light} />
      </div>

      <div className="lane-metric-row">
        <span className="lane-count">{lane.total}</span>
        <span className="lane-tag">{CONGESTION_LABEL[lane.congestion]}</span>
      </div>

      <div className="lane-countdown">{greenSeconds !== null ? `${greenSeconds}s green` : ""}</div>

      <div className="lane-breakdown">
        {Object.entries(lane.counts).map(([label, count]) => (
          <span key={label} className="lane-chip">
            {label}: {count}
          </span>
        ))}
        {Object.keys(lane.counts).length === 0 && <span className="lane-chip empty">no vehicles</span>}
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

      {lane.emergency ? (
        <div className="emergency-detected">Emergency vehicle detected on this lane</div>
      ) : (
        <button className="emergency-btn" onClick={() => onTriggerEmergency(lane.id)}>
          Manual emergency priority
        </button>
      )}
    </div>
  );
}
