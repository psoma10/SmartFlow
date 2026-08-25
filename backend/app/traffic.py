"""Lane geometry, per-lane occupancy and congestion classification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import cv2
import numpy as np

from .config import LaneConfig
from .tracker import TrackState

CONGESTION_LEVELS = ("low", "medium", "high")
_MEDIUM_AT = 0.35
_HIGH_AT = 0.70


@dataclass(frozen=True)
class LaneStats:
    id: str
    name: str
    counts: dict[str, int]
    total: int
    stopped: int
    avg_speed: float
    density: float           # occupancy relative to lane capacity, clipped to [0,1]
    queue_ratio: float       # share of lane occupancy that is standing still
    congestion: str
    cumulative: int          # unique vehicles seen in this lane since reset
    emergency: bool
    emergency_track: int | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "counts": dict(self.counts),
            "total": self.total,
            "stopped": self.stopped,
            "avg_speed": round(self.avg_speed, 4),
            "density": round(self.density, 3),
            "queue_ratio": round(self.queue_ratio, 3),
            "congestion": self.congestion,
            "cumulative": self.cumulative,
            "emergency": self.emergency,
            "emergency_track": self.emergency_track,
        }


class LaneGeometry:
    """Compiled pixel polygons for the current frame size."""

    def __init__(self, lanes: Sequence[LaneConfig], width: int, height: int) -> None:
        self.lanes = tuple(lanes)
        self.width = width
        self.height = height
        self._polygons = {
            lane.id: np.array(
                [(x * width, y * height) for x, y in lane.polygon], dtype=np.float32
            )
            for lane in lanes
        }

    def polygon(self, lane_id: str) -> np.ndarray:
        return self._polygons[lane_id]

    def lane_of(self, point: tuple[float, float]) -> str | None:
        """Return the lane whose zone contains the point, innermost match wins."""
        best: tuple[float, str] | None = None
        for lane_id, polygon in self._polygons.items():
            distance = cv2.pointPolygonTest(polygon, (float(point[0]), float(point[1])), True)
            if distance >= 0 and (best is None or distance > best[0]):
                best = (distance, lane_id)
        return best[1] if best else None


class LaneAnalyzer:
    """Aggregates tracks into per-lane statistics and remembers unique arrivals."""

    def __init__(self, lanes: Sequence[LaneConfig]) -> None:
        self._lanes = tuple(lanes)
        self._capacity = {lane.id: max(1, lane.capacity) for lane in lanes}
        self._seen: dict[str, set[int]] = {lane.id: set() for lane in lanes}

    def reset(self) -> None:
        self._seen = {lane.id: set() for lane in self._lanes}

    def analyze(self, tracks: Iterable[TrackState]) -> tuple[LaneStats, ...]:
        buckets: dict[str, list[TrackState]] = {lane.id: [] for lane in self._lanes}
        for track in tracks:
            if track.lane_id in buckets:
                buckets[track.lane_id].append(track)
                self._seen[track.lane_id].add(track.track_id)

        return tuple(self._stats(lane, buckets[lane.id]) for lane in self._lanes)

    def _stats(self, lane: LaneConfig, tracks: list[TrackState]) -> LaneStats:
        counts: dict[str, int] = {}
        for track in tracks:
            counts[track.label] = counts.get(track.label, 0) + 1

        total = len(tracks)
        stopped = sum(1 for t in tracks if t.stopped)
        avg_speed = float(np.mean([t.speed for t in tracks])) if tracks else 0.0
        density = min(1.0, total / self._capacity[lane.id])
        queue_ratio = stopped / total if total else 0.0
        emergency_track = next((t.track_id for t in tracks if t.is_emergency), None)

        return LaneStats(
            id=lane.id,
            name=lane.name,
            counts=counts,
            total=total,
            stopped=stopped,
            avg_speed=avg_speed,
            density=density,
            queue_ratio=queue_ratio,
            congestion=classify(density),
            cumulative=len(self._seen[lane.id]),
            emergency=emergency_track is not None,
            emergency_track=emergency_track,
        )


def classify(density: float) -> str:
    if density >= _HIGH_AT:
        return "high"
    if density >= _MEDIUM_AT:
        return "medium"
    return "low"
