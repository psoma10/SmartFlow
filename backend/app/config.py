"""Configuration models and persistence for SmartFlow 2.0."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "smartflow.json"
VIDEO_DIR = ROOT / "videos"
MODEL_DIR = ROOT / "models"

Point = tuple[float, float]

# COCO vehicle classes emitted by YOLO11 pretrained weights.
VEHICLE_CLASSES: dict[int, str] = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
# Extra labels that a fine-tuned model may provide for priority vehicles.
EMERGENCY_LABELS = frozenset({"ambulance", "fire_truck", "firetruck", "police", "police_car"})


@dataclass(frozen=True)
class LaneConfig:
    """A directional approach zone, stored in normalized [0,1] frame coordinates."""

    id: str
    name: str
    polygon: tuple[Point, ...]
    capacity: int = 18

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "polygon": [list(p) for p in self.polygon],
            "capacity": self.capacity,
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "LaneConfig":
        polygon = tuple((float(p[0]), float(p[1])) for p in raw["polygon"])
        if len(polygon) < 3:
            raise ValueError(f"lane {raw.get('id')!r} needs at least 3 polygon points")
        for x, y in polygon:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(f"lane {raw.get('id')!r} polygon must be normalized to [0,1]")
        return LaneConfig(
            id=str(raw["id"]),
            name=str(raw.get("name", raw["id"])),
            polygon=polygon,
            capacity=max(1, int(raw.get("capacity", 18))),
        )


@dataclass(frozen=True)
class SignalConfig:
    """Adaptive signal timing envelope and priority weights."""

    min_green: float = 12.0
    max_green: float = 60.0
    yellow: float = 3.0
    all_red: float = 2.0
    weight_density: float = 0.5
    weight_queue: float = 0.3
    weight_wait: float = 0.2
    starvation_seconds: float = 90.0
    emergency_green: float = 18.0
    emergency_clearance: float = 4.0
    manual_emergency_max_seconds: float = 60.0
    baseline_fixed_green: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class DetectorConfig:
    model_path: str = "yolo11n.pt"
    emergency_model_path: str = ""
    tracker: str = "bytetrack.yaml"
    conf: float = 0.30
    iou: float = 0.5
    imgsz: int = 640
    device: str = ""            # "" = auto, "cpu", "mps", "0"
    frame_stride: int = 1       # process every Nth frame
    stopped_speed: float = 0.02  # normalized frame-diagonals per second

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class AppConfig:
    source: str = "videos/traffic.mp4"
    loop_video: bool = True
    target_fps: float = 20.0
    jpeg_quality: int = 75
    # Frames wider than this are downscaled before detection/annotation. A 4K
    # source held as three full-frame copies per cycle (raw/canvas/overlay) is
    # the single largest memory cost in the pipeline — this bounds it on
    # memory-constrained hosts without touching accuracy, since YOLO
    # letterboxes to imgsz regardless of input size.
    max_frame_width: int = 960
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    lanes: tuple[LaneConfig, ...] = field(default_factory=lambda: DEFAULT_LANES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "loop_video": self.loop_video,
            "target_fps": self.target_fps,
            "jpeg_quality": self.jpeg_quality,
            "detector": self.detector.to_dict(),
            "signal": self.signal.to_dict(),
            "lanes": [lane.to_dict() for lane in self.lanes],
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "AppConfig":
        base = AppConfig()
        detector = replace(base.detector, **_filter(raw.get("detector", {}), DetectorConfig))
        signal = replace(base.signal, **_filter(raw.get("signal", {}), SignalConfig))
        lanes = tuple(LaneConfig.from_dict(item) for item in raw.get("lanes", []))
        return AppConfig(
            source=str(raw.get("source", base.source)),
            loop_video=bool(raw.get("loop_video", base.loop_video)),
            target_fps=float(raw.get("target_fps", base.target_fps)),
            jpeg_quality=int(raw.get("jpeg_quality", base.jpeg_quality)),
            detector=detector,
            signal=signal,
            lanes=lanes or base.lanes,
        )


def _filter(raw: dict[str, Any], cls: type) -> dict[str, Any]:
    allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    return {k: v for k, v in raw.items() if k in allowed}


# Default zones: four approaches carved out of the frame. Tune them live from the
# dashboard's lane editor — every deployment has a different camera geometry.
DEFAULT_LANES: tuple[LaneConfig, ...] = (
    LaneConfig("N", "North", ((0.30, 0.02), (0.70, 0.02), (0.62, 0.42), (0.38, 0.42)), 18),
    LaneConfig("E", "East", ((0.72, 0.30), (0.98, 0.22), (0.98, 0.72), (0.68, 0.62)), 18),
    LaneConfig("S", "South", ((0.36, 0.60), (0.66, 0.60), (0.74, 0.98), (0.26, 0.98)), 18),
    LaneConfig("W", "West", ((0.02, 0.24), (0.30, 0.32), (0.32, 0.62), (0.02, 0.74)), 18),
)


def load_config() -> AppConfig:
    if CONFIG_FILE.exists():
        try:
            return AppConfig.from_dict(json.loads(CONFIG_FILE.read_text()))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(f"invalid config at {CONFIG_FILE}: {exc}") from exc
    config = AppConfig(source=os.environ.get("SMARTFLOW_SOURCE", AppConfig.source))
    save_config(config)
    return config


_save_lock = threading.Lock()


def save_config(config: AppConfig) -> AppConfig:
    """Atomic write: a crash or a concurrent writer can never leave a truncated
    config.json behind (which would otherwise brick the next server start)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with _save_lock:
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(config.to_dict(), indent=2))
        tmp.replace(CONFIG_FILE)
    return config
