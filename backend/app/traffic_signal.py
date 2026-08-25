"""Adaptive signal controller: density + queue + waiting-time fairness, with
emergency-vehicle preemption."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .config import LaneConfig, SignalConfig
from .traffic import LaneStats

GREEN, YELLOW, ALL_RED = "green", "yellow", "all_red"


@dataclass(frozen=True)
class LanePriority:
    lane_id: str
    density: float
    queue_ratio: float
    wait_seconds: float
    score: float
    starving: bool

    def to_dict(self) -> dict:
        return {
            "lane_id": self.lane_id,
            "density": round(self.density, 3),
            "queue_ratio": round(self.queue_ratio, 3),
            "wait_seconds": round(self.wait_seconds, 1),
            "score": round(self.score, 4),
            "starving": self.starving,
        }


@dataclass(frozen=True)
class SignalState:
    phase: str
    active_lane: str | None
    next_lane: str | None
    remaining: float
    phase_duration: float
    lane_signals: dict[str, str]
    priorities: tuple[LanePriority, ...]
    emergency_lane: str | None
    emergency_active: bool
    cycle: int
    served: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "active_lane": self.active_lane,
            "next_lane": self.next_lane,
            "remaining": round(self.remaining, 1),
            "phase_duration": round(self.phase_duration, 1),
            "lane_signals": dict(self.lane_signals),
            "priorities": [p.to_dict() for p in self.priorities],
            "emergency_lane": self.emergency_lane,
            "emergency_active": self.emergency_active,
            "cycle": self.cycle,
            "served": dict(self.served),
        }


class AdaptiveSignalController:
    """Acyclic, priority-driven controller.

    Every phase end re-scores all approaches; the winner gets a green whose
    length scales with its score. Waiting time is part of the score and a hard
    starvation guard forces long-waiting approaches through, so a quiet road
    can never be starved by a busy one.
    """

    def __init__(self, lanes: Sequence[LaneConfig], config: SignalConfig) -> None:
        self._lane_ids = tuple(lane.id for lane in lanes)
        self._config = config
        self.reset()

    def reset(self) -> None:
        first = self._lane_ids[0] if self._lane_ids else None
        self._phase = GREEN
        self._active = first
        self._pending: str | None = None
        self._remaining = self._config.min_green
        self._phase_duration = self._config.min_green
        self._wait = {lane_id: 0.0 for lane_id in self._lane_ids}
        self._served = {lane_id: 0 for lane_id in self._lane_ids}
        self._cycle = 1
        self._emergency_lane: str | None = None
        self._emergency_hold = 0.0
        self._manual_emergency: str | None = None
        self._manual_age = 0.0
        self._priorities: tuple[LanePriority, ...] = ()

    # ---- external triggers -------------------------------------------------
    def trigger_emergency(self, lane_id: str) -> None:
        if lane_id in self._wait:
            self._manual_emergency = lane_id
            self._manual_age = 0.0

    def clear_emergency(self) -> None:
        self._manual_emergency = None
        self._manual_age = 0.0
        self._emergency_hold = 0.0
        self._emergency_lane = None

    # ---- main tick ---------------------------------------------------------
    def step(self, dt: float, lane_stats: Sequence[LaneStats]) -> SignalState:
        stats = {s.id: s for s in lane_stats}
        self._accumulate_wait(dt)
        self._priorities = self._score(stats)

        if self._manual_emergency:
            # An operator's manual trigger must not be able to gridlock the
            # intersection forever if nobody presses Clear.
            self._manual_age += dt
            if self._manual_age >= self._config.manual_emergency_max_seconds:
                self._manual_emergency = None
                self._manual_age = 0.0

        detected = next((s.id for s in lane_stats if s.emergency), None)
        emergency_lane = self._manual_emergency or detected
        self._update_emergency(dt, emergency_lane)

        green_elapsed = self._phase_duration - self._remaining
        can_preempt = self._phase == GREEN and green_elapsed >= self._config.min_green

        self._remaining -= dt
        if self._emergency_lane and can_preempt and self._active != self._emergency_lane:
            # Preempt: cut the running green short (but never below min_green,
            # so a flickering detection can't collapse the phase to near-zero)
            # and route to the emergency approach.
            self._pending = self._emergency_lane
            self._begin(YELLOW, self._config.yellow)
        elif self._remaining <= 0.0:
            self._advance(stats)

        return self._snapshot()

    def _accumulate_wait(self, dt: float) -> None:
        for lane_id in self._lane_ids:
            if lane_id == self._active and self._phase == GREEN:
                self._wait[lane_id] = 0.0
            else:
                self._wait[lane_id] += dt

    def _update_emergency(self, dt: float, emergency_lane: str | None) -> None:
        if emergency_lane:
            self._emergency_lane = emergency_lane
            self._emergency_hold = self._config.emergency_clearance
            return
        if self._emergency_hold > 0.0:
            # Keep the corridor open briefly after the vehicle leaves the frame.
            self._emergency_hold = max(0.0, self._emergency_hold - dt)
            if self._emergency_hold == 0.0:
                self._emergency_lane = None

    def _advance(self, stats: dict[str, LaneStats]) -> None:
        if self._phase == GREEN:
            self._pending = self._pending or self._select(stats)
            self._begin(YELLOW, self._config.yellow)
        elif self._phase == YELLOW:
            self._begin(ALL_RED, self._config.all_red)
        else:
            target = self._pending or self._select(stats)
            if self._lane_ids and target == self._lane_ids[0]:
                self._cycle += 1
            self._active = target
            self._pending = None
            self._served[target] = self._served.get(target, 0) + 1
            self._begin(GREEN, self._green_time(target))

    def _begin(self, phase: str, duration: float) -> None:
        self._phase = phase
        self._phase_duration = duration
        self._remaining = duration

    def _select(self, stats: dict[str, LaneStats]) -> str:
        if self._emergency_lane:
            return self._emergency_lane
        candidates = [p for p in self._priorities if p.lane_id != self._active] or list(self._priorities)
        starving = [p for p in candidates if p.starving]
        pool = starving or candidates
        if not pool:
            return self._active or self._lane_ids[0]
        return max(pool, key=lambda p: (p.score, p.wait_seconds)).lane_id

    def _green_time(self, lane_id: str) -> float:
        config = self._config
        if self._emergency_lane == lane_id:
            return config.emergency_green
        # Absolute demand, not share-of-the-winner: the winning lane's score is
        # near the theoretical max (weight_density + weight_queue*1 + weight_wait)
        # only under real congestion, so scaling by it made every empty
        # intersection get max_green. Scale by the score's own ceiling instead.
        scores = {p.lane_id: p.score for p in self._priorities}
        ceiling = config.weight_density + config.weight_queue + config.weight_wait
        share = min(1.0, scores.get(lane_id, 0.0) / ceiling) if ceiling > 0 else 0.0
        span = max(0.0, config.max_green - config.min_green)
        return round(config.min_green + share * span, 1)

    def _score(self, stats: dict[str, LaneStats]) -> tuple[LanePriority, ...]:
        config = self._config
        priorities = []
        for lane_id in self._lane_ids:
            stat = stats.get(lane_id)
            density = stat.density if stat else 0.0
            queue = stat.queue_ratio if stat else 0.0
            wait = self._wait[lane_id]
            wait_norm = min(1.0, wait / config.starvation_seconds) if config.starvation_seconds > 0 else 0.0
            score = (
                config.weight_density * density
                + config.weight_queue * queue * density
                + config.weight_wait * wait_norm
            )
            priorities.append(
                LanePriority(
                    lane_id=lane_id,
                    density=density,
                    queue_ratio=queue,
                    wait_seconds=wait,
                    score=score,
                    starving=wait >= config.starvation_seconds,
                )
            )
        return tuple(priorities)

    def _snapshot(self) -> SignalState:
        signals = {lane_id: "red" for lane_id in self._lane_ids}
        if self._active and self._phase in (GREEN, YELLOW):
            signals[self._active] = self._phase
        return SignalState(
            phase=self._phase,
            active_lane=self._active,
            next_lane=self._pending,
            remaining=max(0.0, self._remaining),
            phase_duration=self._phase_duration,
            lane_signals=signals,
            priorities=self._priorities,
            emergency_lane=self._emergency_lane,
            emergency_active=self._emergency_lane is not None,
            cycle=self._cycle,
            served=dict(self._served),
        )
