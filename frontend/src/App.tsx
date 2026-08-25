import { useCallback, useEffect, useRef, useState } from "react";
import { connectTelemetry, triggerEmergency } from "./lib/api";
import type { TelemetryFrame } from "./lib/types";
import { VideoStream } from "./components/VideoStream";
import { LaneCard } from "./components/LaneCard";
import { SignalPanel } from "./components/SignalPanel";
import { TrafficChart, type HistoryPoint } from "./components/TrafficChart";
import "./App.css";

const HISTORY_LENGTH = 60;

function App() {
  const [frame, setFrame] = useState<TelemetryFrame | null>(null);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const tickRef = useRef(0);

  useEffect(() => {
    const disconnect = connectTelemetry(
      (next) => {
        setFrame(next);
        tickRef.current += 1;
        setHistory((prev) => {
          const point: HistoryPoint = { t: tickRef.current };
          for (const lane of next.lanes) point[lane.id] = lane.total;
          const updated = [...prev, point];
          return updated.length > HISTORY_LENGTH ? updated.slice(-HISTORY_LENGTH) : updated;
        });
      },
      setConnected,
    );
    return disconnect;
  }, []);

  const handleTrigger = useCallback((laneId: string) => {
    triggerEmergency(laneId).catch((err) => console.error("emergency trigger failed", err));
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>SmartFlow 2.0</h1>
          <p>Adaptive traffic signal optimization — lane-level congestion, waiting-time fairness, emergency priority.</p>
        </div>
        <span className={`conn-pill ${connected ? "ok" : "down"}`}>
          {connected ? "Telemetry connected" : "Reconnecting…"}
        </span>
      </header>

      <main className="app-grid">
        <section className="app-video-col">
          <VideoStream connected={connected} emergencyLane={frame?.signal.emergency_active ? frame.signal.emergency_lane : null} />
          {frame && (
            <SignalPanel signal={frame.signal} vehicleCount={frame.vehicle_count} fps={frame.fps} />
          )}
          {frame && <TrafficChart history={history} lanes={frame.lanes} />}
        </section>

        <section className="app-lanes-col">
          {frame ? (
            frame.lanes.map((lane) => (
              <LaneCard key={lane.id} lane={lane} signal={frame.signal} onTriggerEmergency={handleTrigger} />
            ))
          ) : (
            <div className="lane-card placeholder">Waiting for telemetry…</div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
