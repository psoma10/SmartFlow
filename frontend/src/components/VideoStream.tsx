import { useState } from "react";
import { streamUrl } from "../lib/api";

interface Props {
  connected: boolean;
  emergencyLane: string | null;
}

/** MJPEG feed from /api/stream, annotated server-side with boxes + lane zones.
 * The emergency banner is rendered here (DOM), not baked into the JPEG —
 * baked text over unpredictable video backgrounds is often unreadable. */
export function VideoStream({ connected, emergencyLane }: Props) {
  const [errored, setErrored] = useState(false);

  return (
    <div className="video-panel">
      <div className="video-frame">
        {errored ? (
          <div className="video-placeholder">Waiting for video source…</div>
        ) : (
          <img
            src={streamUrl}
            alt="SmartFlow live traffic feed"
            onError={() => setErrored(true)}
            onLoad={() => setErrored(false)}
          />
        )}
        <span className={`live-badge ${connected ? "live" : "stale"}`}>
          {connected ? "LIVE" : "RECONNECTING"}
        </span>
        {emergencyLane && (
          <>
            <div className="video-emergency-ring" />
            <span className="video-emergency-label">EMERGENCY CORRIDOR — LANE {emergencyLane}</span>
          </>
        )}
      </div>
    </div>
  );
}
