"""YOLO11 detection + ByteTrack multi-object tracking wrapper."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import EMERGENCY_LABELS, MODEL_DIR, VEHICLE_CLASSES, DetectorConfig

log = logging.getLogger("smartflow.detector")


@dataclass(frozen=True)
class Detection:
    """One tracked vehicle in one frame. Pixel coordinates."""

    track_id: int
    label: str
    conf: float
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    is_priority_class: bool = False

    @property
    def anchor(self) -> tuple[float, float]:
        """Bottom-center of the box — the point that touches the road plane."""
        x1, _, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, y2)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


class VehicleDetector:
    """Runs YOLO11 with a persistent ByteTrack association across frames.

    A second optional model can be supplied for emergency-vehicle classes; when
    absent the pipeline falls back to the flashing-beacon heuristic.
    """

    def __init__(self, config: DetectorConfig) -> None:
        from ._lzma_shim import ensure_lzma_importable

        ensure_lzma_importable()
        from ultralytics import YOLO  # imported lazily: heavy dependency

        self._config = config
        self._model = YOLO(_resolve_weights(config.model_path))
        self._names: dict[int, str] = dict(self._model.names)
        self._emergency_model = None
        if config.emergency_model_path:
            path = _resolve_weights(config.emergency_model_path)
            if Path(path).exists():
                self._emergency_model = YOLO(path)
                log.info("emergency model loaded: %s", path)
            else:
                log.warning("emergency model not found, using beacon heuristic: %s", path)

    @property
    def has_emergency_model(self) -> bool:
        return self._emergency_model is not None

    def reset(self) -> None:
        """Drop tracker state — call when the video source rewinds or changes."""
        predictor = getattr(self._model, "predictor", None)
        trackers = getattr(predictor, "trackers", None) if predictor else None
        if trackers:
            for tracker in trackers:
                tracker.reset()

    def track(self, frame: np.ndarray) -> tuple[Detection, ...]:
        results = self._model.track(
            frame,
            persist=True,
            tracker=self._config.tracker,
            conf=self._config.conf,
            iou=self._config.iou,
            imgsz=self._config.imgsz,
            device=self._config.device or None,
            classes=sorted(VEHICLE_CLASSES),
            verbose=False,
        )
        detections = _to_detections(results[0], self._names)
        if self._emergency_model is not None:
            detections = self._merge_emergency(frame, detections)
        return detections

    def _merge_emergency(self, frame: np.ndarray, detections: tuple[Detection, ...]) -> tuple[Detection, ...]:
        """Flag tracked vehicles that overlap a priority-class box from the second model."""
        assert self._emergency_model is not None
        result = self._emergency_model.predict(
            frame, conf=self._config.conf, imgsz=self._config.imgsz,
            device=self._config.device or None, verbose=False,
        )[0]
        names = dict(self._emergency_model.names)
        priority_boxes = [
            tuple(float(v) for v in box.xyxy[0].tolist())
            for box in (result.boxes or [])
            if names.get(int(box.cls[0]), "").lower().replace(" ", "_") in EMERGENCY_LABELS
        ]
        if not priority_boxes:
            return detections
        return tuple(
            Detection(
                track_id=det.track_id,
                label=det.label,
                conf=det.conf,
                bbox=det.bbox,
                is_priority_class=any(_iou(det.bbox, box) > 0.35 for box in priority_boxes),
            )
            for det in detections
        )


def _to_detections(result, names: dict[int, str]) -> tuple[Detection, ...]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or boxes.id is None:
        return ()
    xyxy = boxes.xyxy.cpu().numpy()
    ids = boxes.id.int().cpu().numpy()
    cls = boxes.cls.int().cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    detections = []
    for box, track_id, class_id, score in zip(xyxy, ids, cls, conf):
        label = VEHICLE_CLASSES.get(int(class_id), names.get(int(class_id), "vehicle"))
        detections.append(
            Detection(
                track_id=int(track_id),
                label=label,
                conf=float(score),
                bbox=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
            )
        )
    return tuple(detections)


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0.0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _resolve_weights(path: str) -> str:
    """Prefer models/ for local weights; otherwise let ultralytics fetch by name."""
    candidate = Path(path)
    if candidate.is_absolute() or candidate.exists():
        return str(candidate)
    local = MODEL_DIR / candidate.name
    if local.exists():
        return str(local)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return path
