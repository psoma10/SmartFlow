"""Frame-by-frame processing loop: detect, track, analyze lanes, drive signal."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import AppConfig, DetectorConfig
from .detector import VehicleDetector
from .traffic import LaneAnalyzer, LaneGeometry, LaneStats
from .traffic_signal import AdaptiveSignalController, SignalState
from .tracker import TrackRegistry, TrackState

log = logging.getLogger("smartflow.pipeline")

LANE_COLORS = {
    "low": (60, 200, 60),
    "medium": (0, 200, 235),
    "high": (0, 0, 235),
}


@dataclass(frozen=True)
class FrameResult:
    frame: np.ndarray
    tracks: tuple[TrackState, ...]
    lanes: tuple[LaneStats, ...]
    signal: SignalState
    frame_index: int
    timestamp: float
    fps: float


class VideoSource:
    """Wraps VideoCapture with optional looping and a resolved source path."""

    def __init__(self, source: str, loop: bool) -> None:
        self._source = _resolve_source(source)
        self._loop = loop
        self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open video source: {self._source}")
        self._just_looped = False

    @property
    def size(self) -> tuple[int, int]:
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
        return width, height

    def read(self) -> np.ndarray | None:
        self._just_looped = False
        ok, frame = self._cap.read()
        if ok:
            return frame
        if self._loop and str(self._source).isdigit() is False:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
            self._just_looped = ok
            return frame if ok else None
        return None

    def consume_loop_flag(self) -> bool:
        """True exactly once per rewind — track/lane state must reset on this."""
        looped, self._just_looped = self._just_looped, False
        return looped

    def release(self) -> None:
        self._cap.release()


def _resolve_source(source: str) -> str | int:
    if source.isdigit():
        return int(source)
    if "://" in source:
        return source  # network stream (rtsp/http/...) — never filesystem-joined
    path = Path(source)
    if not path.is_absolute():
        from .config import ROOT

        path = ROOT / source
    return str(path)


class TrafficPipeline:
    """Owns the video loop, detector, tracker, lane analyzer and signal controller.

    Runs on a background thread and publishes the latest FrameResult; the API
    layer (HTTP + WebSocket) only ever reads that shared, lock-protected state.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._detector = VehicleDetector(config.detector)
        self._registry = TrackRegistry(config.detector.stopped_speed)
        self._analyzer = LaneAnalyzer(config.lanes)
        self._signal = AdaptiveSignalController(config.lanes, config.signal)
        self._source = VideoSource(config.source, config.loop_video)
        self._frame_size = self._source.size  # cached: avoid querying VideoCapture from another thread
        self._geometry = LaneGeometry(config.lanes, *self._frame_size)

        self._lock = threading.Lock()
        self._latest: FrameResult | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame_index = 0
        self._error: str | None = None

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="smartflow-pipeline")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        self._source.release()

    def latest(self) -> FrameResult | None:
        with self._lock:
            return self._latest

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def config(self) -> AppConfig:
        return self._config

    # -- controls ---------------------------------------------------------
    def trigger_emergency(self, lane_id: str) -> None:
        self._signal.trigger_emergency(lane_id)

    def clear_emergency(self) -> None:
        self._signal.clear_emergency()

    def reload_lanes(self, config: AppConfig) -> None:
        with self._lock:
            self._config = config
            self._analyzer = LaneAnalyzer(config.lanes)
            self._signal = AdaptiveSignalController(config.lanes, config.signal)
            self._geometry = LaneGeometry(config.lanes, *self._frame_size)

    # -- main loop ----------------------------------------------------------
    def _run(self) -> None:
        target_dt = 1.0 / max(1.0, self._config.target_fps)
        last_tick = time.monotonic()
        fps_ema = self._config.target_fps

        while self._running:
            loop_start = time.monotonic()
            frame = self._source.read()
            if frame is None:
                log.info("video source exhausted, stopping pipeline")
                self._running = False
                break

            try:
                detections = self._detector.track(frame)
            except Exception as exc:  # noqa: BLE001 - surface to API, keep loop alive
                self._error = str(exc)
                log.exception("detector failure")
                last_tick = time.monotonic()  # don't let retry time leak into signal dt on recovery
                time.sleep(0.5)
                continue
            self._error = None

            now = time.monotonic()
            dt = now - last_tick
            last_tick = now

            with self._lock:
                geometry = self._geometry
                analyzer = self._analyzer
                signal = self._signal

            if self._source.consume_loop_flag():
                # Track IDs and lane state don't survive a rewind meaningfully:
                # ByteTrack will re-associate end-of-clip vehicles with
                # start-of-clip ones, corrupting dwell time, cumulative counts
                # and any latched emergency flag.
                self._detector.reset()
                self._registry.reset()
                analyzer.reset()

            tracks = self._registry.update(
                detections, frame, now, geometry.lane_of,
                use_beacon=not self._detector.has_emergency_model,
            )
            lane_stats = analyzer.analyze(tracks)
            signal_state = signal.step(dt, lane_stats)
            annotated = _annotate(frame, tracks, lane_stats, signal_state, geometry)

            self._frame_index += 1
            elapsed = time.monotonic() - loop_start
            fps_ema = 0.9 * fps_ema + 0.1 * (1.0 / elapsed if elapsed > 0 else fps_ema)

            with self._lock:
                self._latest = FrameResult(
                    frame=annotated,
                    tracks=tracks,
                    lanes=lane_stats,
                    signal=signal_state,
                    frame_index=self._frame_index,
                    timestamp=now,
                    fps=fps_ema,
                )

            sleep_left = target_dt - (time.monotonic() - loop_start)
            if sleep_left > 0:
                time.sleep(sleep_left)


_FILL_ALPHA = {"low": 0.0, "medium": 0.18, "high": 0.28}
_NEUTRAL_BOX = (248, 189, 56)      # BGR for accent cyan #38bdf8 — reserves green/yellow/red for signal state
_EMERGENCY_BOX = (66, 135, 245)    # BGR for emergency orange, distinct from congestion palette


def _annotate(frame: np.ndarray, tracks: tuple[TrackState, ...], lanes: tuple[LaneStats, ...],
              signal: SignalState, geometry: LaneGeometry) -> np.ndarray:
    canvas = frame.copy()
    overlay = canvas.copy()

    # Only paint zones that actually need attention — filling every lane the same
    # green when traffic is light just tints the whole frame and hides the scene.
    for lane in lanes:
        alpha = _FILL_ALPHA[lane.congestion]
        if alpha <= 0.0:
            continue
        polygon = geometry.polygon(lane.id).astype(np.int32)
        cv2.fillPoly(overlay, [polygon], LANE_COLORS[lane.congestion])
        cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, dst=canvas)
        overlay = canvas.copy()

    for lane in lanes:
        polygon = geometry.polygon(lane.id).astype(np.int32)
        color = LANE_COLORS[lane.congestion]
        cv2.polylines(canvas, [polygon], True, color, 2)
        cx, cy = polygon.mean(axis=0).astype(int)
        signal_color = _signal_color(signal.lane_signals.get(lane.id, "red"))
        cv2.circle(canvas, (cx, cy - 16), 10, signal_color, -1)
        label = f"{lane.name}: {lane.total} ({lane.congestion})"
        (text_w, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.putText(canvas, label, (cx - text_w // 2, cy + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    for track in tracks:
        x1, y1, x2, y2 = (int(v) for v in track.bbox)
        box_color = _EMERGENCY_BOX if track.is_emergency else _NEUTRAL_BOX
        cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2)
        tag = f"#{track.track_id} {track.label}"
        if track.is_emergency:
            tag += " EMERGENCY"
        cv2.putText(canvas, tag, (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

    return canvas


def _signal_color(state: str) -> tuple[int, int, int]:
    return {"green": (0, 220, 0), "yellow": (0, 220, 235), "red": (0, 0, 235)}.get(state, (0, 0, 235))
