import type { SignalState } from "../lib/types";
import { clearEmergency } from "../lib/api";

interface Props {
  signal: SignalState;
  vehicleCount: number;
  fps: number;
}

const PHASE_LABEL: Record<SignalState["phase"], string> = {
  green: "GREEN",
  yellow: "YELLOW",
  all_red: "ALL RED",
};

export function SignalPanel({ signal, vehicleCount, fps }: Props) {
  return (
    <div className="signal-panel">
      <div className="signal-panel-main">
        <div>
          <span className="signal-phase-label">{PHASE_LABEL[signal.phase]}</span>
          <span className="signal-active-lane">
            {signal.active_lane ? `Lane ${signal.active_lane}` : "—"}
          </span>
        </div>
        <div className="signal-countdown">{Math.ceil(signal.remaining)}s</div>
      </div>

      <div className="signal-meta-row">
        <span>Cycle {signal.cycle}</span>
        <span>{vehicleCount} vehicles tracked</span>
        <span>{fps} fps</span>
      </div>

      {signal.emergency_active && (
        <div className="emergency-banner">
          <span>Emergency corridor: lane {signal.emergency_lane}</span>
          <button onClick={() => clearEmergency()}>Clear</button>
        </div>
      )}
    </div>
  );
}
