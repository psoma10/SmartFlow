export interface LaneStats {
  id: string;
  name: string;
  counts: Record<string, number>;
  total: number;
  stopped: number;
  avg_speed: number;
  density: number;
  queue_ratio: number;
  congestion: "low" | "medium" | "high";
  cumulative: number;
  emergency: boolean;
  emergency_track: number | null;
}

export interface LanePriority {
  lane_id: string;
  density: number;
  queue_ratio: number;
  wait_seconds: number;
  score: number;
  starving: boolean;
}

export interface SignalState {
  phase: "green" | "yellow" | "all_red";
  active_lane: string | null;
  next_lane: string | null;
  remaining: number;
  phase_duration: number;
  lane_signals: Record<string, "green" | "yellow" | "red">;
  priorities: LanePriority[];
  emergency_lane: string | null;
  emergency_active: boolean;
  cycle: number;
  served: Record<string, number>;
}

export interface TelemetryFrame {
  frame_index: number;
  fps: number;
  lanes: LaneStats[];
  signal: SignalState;
  vehicle_count: number;
}

export interface HealthResponse {
  status: "starting" | "running" | "error";
  error: string | null;
  frame_index: number;
  fps: number;
}

export interface VideoSourceOption {
  id: string;
  label: string;
}

export interface SourcesResponse {
  sources: VideoSourceOption[];
  active: string;
}
