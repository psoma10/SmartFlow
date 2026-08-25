"""Per-track memory: lane membership, speed, dwell time and beacon evidence."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace
from typing import Iterable

import cv2
import numpy as np

from .detector import Detection

# Beacon heuristic tuning. A roof beacon alternates saturated red and blue in the
# upper part of the vehicle box, so we look for both colours present over a short
# window AND a temporal swing in at least one of them.
_BEACON_WINDOW = 24
_BEACON_MIN_PEAK = 0.035
_BEACON_MIN_SWING = 0.020
_MIN_BEACON_SAMPLES = 8
_HISTORY = 12


@dataclass(frozen=True)
class TrackState:
    track_id: int
    label: str
    bbox: tuple[float, float, float, float]
    anchor: tuple[float, float]
    lane_id: str | None
    speed: float          # frame-diagonals per second
    stopped: bool
    first_seen: float
    last_seen: float
    beacon_score: float
    is_emergency: bool

    @property
    def dwell(self) -> float:
        return max(0.0, self.last_seen - self.first_seen)


class _TrackMemory:
    __slots__ = ("first_seen", "positions", "beacon", "label_votes", "priority_hits")

    def __init__(self, now: float) -> None:
        self.first_seen = now
        self.positions: deque[tuple[float, float, float]] = deque(maxlen=_HISTORY)
        self.beacon: deque[tuple[float, float]] = deque(maxlen=_BEACON_WINDOW)
        self.label_votes: dict[str, int] = {}
        self.priority_hits = 0


class TrackRegistry:
    """Turns per-frame detections into stateful tracks with derived kinematics."""

    def __init__(self, stopped_speed: float, expiry_seconds: float = 2.0) -> None:
        self._stopped_speed = stopped_speed
        self._expiry = expiry_seconds
        self._memory: dict[int, _TrackMemory] = {}

    def reset(self) -> None:
        self._memory = {}

    def update(
        self,
        detections: Iterable[Detection],
        frame: np.ndarray,
        now: float,
        lane_of: "callable[[tuple[float, float]], str | None]",
        use_beacon: bool,
    ) -> tuple[TrackState, ...]:
        height, width = frame.shape[:2]
        diagonal = math.hypot(width, height) or 1.0
        states: list[TrackState] = []
        seen: set[int] = set()

        for det in detections:
            seen.add(det.track_id)
            memory = self._memory.get(det.track_id)
            if memory is None:
                memory = _TrackMemory(now)
                self._memory[det.track_id] = memory

            memory.label_votes[det.label] = memory.label_votes.get(det.label, 0) + 1
            label = max(memory.label_votes.items(), key=lambda kv: kv[1])[0]

            anchor = det.anchor
            speed = _speed(memory.positions, anchor, now, diagonal)
            memory.positions.append((anchor[0], anchor[1], now))

            beacon_score = 0.0
            if use_beacon:
                memory.beacon.append(_beacon_sample(frame, det.bbox))
                beacon_score = _beacon_score(memory.beacon)
            if det.is_priority_class:
                memory.priority_hits += 1

            is_emergency = memory.priority_hits >= 3 or beacon_score >= 1.0
            states.append(
                TrackState(
                    track_id=det.track_id,
                    label=label,
                    bbox=det.bbox,
                    anchor=anchor,
                    lane_id=lane_of(anchor),
                    speed=speed,
                    stopped=speed <= self._stopped_speed,
                    first_seen=memory.first_seen,
                    last_seen=now,
                    beacon_score=beacon_score,
                    is_emergency=is_emergency,
                )
            )

        self._expire(seen, now)
        return tuple(states)

    def _expire(self, seen: set[int], now: float) -> None:
        stale = [
            track_id
            for track_id, memory in self._memory.items()
            if track_id not in seen and memory.positions and now - memory.positions[-1][2] > self._expiry
        ]
        for track_id in stale:
            del self._memory[track_id]


def _speed(positions: deque[tuple[float, float, float]], anchor: tuple[float, float],
           now: float, diagonal: float) -> float:
    if not positions:
        return 0.0
    x0, y0, t0 = positions[0]
    dt = now - t0
    if dt <= 1e-3:
        return 0.0
    return math.hypot(anchor[0] - x0, anchor[1] - y0) / diagonal / dt


def _beacon_sample(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """Fraction of saturated red and blue pixels in the roof region of the box."""
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, x2 = int(max(0, x1)), int(min(width, x2))
    y1 = int(max(0, y1))
    y2 = int(min(height, y1 + max(4.0, (y2 - y1) * 0.45)))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return (0.0, 0.0)
    roof = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roof, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    bright = (sat > 110) & (val > 140)
    red = bright & ((hue <= 10) | (hue >= 170))
    blue = bright & (hue >= 100) & (hue <= 130)
    total = float(roof.shape[0] * roof.shape[1]) or 1.0
    return (float(red.sum()) / total, float(blue.sum()) / total)


def _beacon_score(samples: deque[tuple[float, float]]) -> float:
    """Score >= 1.0 means the roof shows an alternating red/blue beacon."""
    if len(samples) < _MIN_BEACON_SAMPLES:
        return 0.0
    reds = np.array([s[0] for s in samples], dtype=np.float32)
    blues = np.array([s[1] for s in samples], dtype=np.float32)
    peak = min(float(reds.max()), float(blues.max()))
    swing = max(float(reds.max() - reds.min()), float(blues.max() - blues.min()))
    if peak < _BEACON_MIN_PEAK or swing < _BEACON_MIN_SWING:
        return round(min(0.99, peak / _BEACON_MIN_PEAK * 0.5 + swing / _BEACON_MIN_SWING * 0.4), 3)
    return round(1.0 + min(1.0, peak / _BEACON_MIN_PEAK * 0.25), 3)
