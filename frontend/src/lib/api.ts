import type { HealthResponse, SourcesResponse, TelemetryFrame } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export const streamUrl = `${API_BASE}/api/stream`;

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`health check failed: ${res.status}`);
  return res.json();
}

export async function triggerEmergency(laneId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/emergency/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lane_id: laneId }),
  });
  if (!res.ok) throw new Error(`trigger failed: ${res.status}`);
}

export async function clearEmergency(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/emergency/clear`, { method: "POST" });
  if (!res.ok) throw new Error(`clear failed: ${res.status}`);
}

export async function fetchSources(): Promise<SourcesResponse> {
  const res = await fetch(`${API_BASE}/api/sources`);
  if (!res.ok) throw new Error(`sources fetch failed: ${res.status}`);
  return res.json();
}

export async function switchSource(source: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/config/source`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });
  if (!res.ok) throw new Error(`source switch failed: ${res.status}`);
}

type TelemetryHandler = (frame: TelemetryFrame) => void;

/** Opens the telemetry WebSocket and reconnects with backoff on drop. */
export function connectTelemetry(onFrame: TelemetryHandler, onStatus: (connected: boolean) => void): () => void {
  const wsBase = API_BASE.replace(/^http/, "ws");
  let socket: WebSocket | null = null;
  let closedByCaller = false;
  let retryDelay = 1000;

  const connect = () => {
    socket = new WebSocket(`${wsBase}/ws/telemetry`);
    socket.onopen = () => {
      retryDelay = 1000;
      onStatus(true);
    };
    socket.onmessage = (event) => {
      try {
        onFrame(JSON.parse(event.data) as TelemetryFrame);
      } catch {
        // ignore malformed frame, next tick will recover
      }
    };
    socket.onclose = () => {
      onStatus(false);
      if (!closedByCaller) {
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 8000);
      }
    };
    socket.onerror = () => socket?.close();
  };

  connect();
  return () => {
    closedByCaller = true;
    socket?.close();
  };
}
