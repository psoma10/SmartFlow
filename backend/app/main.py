"""FastAPI app: MJPEG video stream, WebSocket telemetry, control + config API."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import replace

import cv2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .config import AppConfig, LaneConfig, load_config, save_config
from .pipeline import TrafficPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smartflow.api")

state: dict[str, TrafficPipeline] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    pipeline = TrafficPipeline(config)
    pipeline.start()
    state["pipeline"] = pipeline
    log.info("SmartFlow pipeline started, source=%s", config.source)
    yield
    pipeline.stop()


app = FastAPI(title="SmartFlow 2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pipeline() -> TrafficPipeline:
    pipeline = state.get("pipeline")
    if pipeline is None:
        raise HTTPException(503, "pipeline not started")
    return pipeline


@app.get("/api/health")
def health() -> dict:
    pipeline = _pipeline()
    latest = pipeline.latest()
    return {
        "status": "error" if pipeline.error else ("running" if latest else "starting"),
        "error": pipeline.error,
        "frame_index": latest.frame_index if latest else 0,
        "fps": round(latest.fps, 1) if latest else 0.0,
    }


@app.get("/api/state")
def api_state() -> dict:
    pipeline = _pipeline()
    latest = pipeline.latest()
    if latest is None:
        return {"ready": False}
    return {
        "ready": True,
        "frame_index": latest.frame_index,
        "fps": round(latest.fps, 1),
        "lanes": [lane.to_dict() for lane in latest.lanes],
        "signal": latest.signal.to_dict(),
        "vehicle_count": len(latest.tracks),
    }


@app.get("/api/config")
def get_config() -> dict:
    return _pipeline_config().to_dict()


def _pipeline_config() -> AppConfig:
    return _pipeline().config


class LaneUpdate(BaseModel):
    id: str
    name: str
    polygon: list[tuple[float, float]] = Field(min_length=3)
    capacity: int = Field(ge=1, le=200)


class LanesPayload(BaseModel):
    lanes: list[LaneUpdate] = Field(min_length=1)

    @field_validator("lanes")
    @classmethod
    def unique_ids(cls, lanes: list[LaneUpdate]) -> list[LaneUpdate]:
        ids = [lane.id for lane in lanes]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate lane ids in payload: {ids}")
        return lanes


@app.put("/api/config/lanes")
def update_lanes(payload: LanesPayload) -> dict:
    pipeline = _pipeline()
    current = _pipeline_config()
    try:
        lanes = tuple(LaneConfig.from_dict(item.model_dump()) for item in payload.lanes)
    except (ValueError, IndexError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    updated = replace(current, lanes=lanes)
    save_config(updated)
    pipeline.reload_lanes(updated)
    return updated.to_dict()


class EmergencyPayload(BaseModel):
    lane_id: str


@app.post("/api/emergency/trigger")
def trigger_emergency(payload: EmergencyPayload) -> dict:
    pipeline = _pipeline()
    lane_ids = {lane.id for lane in _pipeline_config().lanes}
    if payload.lane_id not in lane_ids:
        raise HTTPException(404, f"unknown lane {payload.lane_id!r}")
    pipeline.trigger_emergency(payload.lane_id)
    return {"ok": True, "lane_id": payload.lane_id}


@app.post("/api/emergency/clear")
def clear_emergency() -> dict:
    _pipeline().clear_emergency()
    return {"ok": True}


@app.get("/api/stream")
def stream() -> StreamingResponse:
    pipeline = _pipeline()
    quality = _pipeline_config().jpeg_quality

    def generate():
        boundary = b"--frame"
        last_index = -1
        while True:
            result = pipeline.latest()
            if result is None or result.frame_index == last_index:
                time.sleep(0.01)  # avoid pegging a threadpool worker at 100% CPU
                continue
            last_index = result.frame_index
            ok, buf = cv2.imencode(".jpg", result.frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                continue
            yield (
                boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(buf)).encode() + b"\r\n\r\n" + buf.tobytes() + b"\r\n"
            )

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket) -> None:
    pipeline = state.get("pipeline")
    if pipeline is None:
        await ws.close(code=1013)  # "try again later" — lifespan hasn't started the pipeline yet
        return

    await ws.accept()
    last_index = -1
    try:
        while True:
            result = pipeline.latest()
            if result is not None and result.frame_index != last_index:
                last_index = result.frame_index
                payload = {
                    "frame_index": result.frame_index,
                    "fps": round(result.fps, 1),
                    "lanes": [lane.to_dict() for lane in result.lanes],
                    "signal": result.signal.to_dict(),
                    "vehicle_count": len(result.tracks),
                }
                await ws.send_text(json.dumps(payload))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        log.debug("telemetry client disconnected")
    except Exception:  # noqa: BLE001 - a dead/broken socket must not leak this loop forever
        log.debug("telemetry send failed, dropping client", exc_info=True)
