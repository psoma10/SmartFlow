# SmartFlow 2.0

SmartFlow 2.0 is an AI-powered adaptive traffic signal optimization system. It uses YOLO11 vehicle detection and ByteTrack tracking to analyze lane-wise congestion in real time, then allocates adaptive green-light duration based on priority scores that balance waiting-time fairness across lanes. The system includes emergency-vehicle preemption via roof-beacon color detection and an optional fine-tuned classification model for emergency vehicle identification.

## Architecture

**Backend** (Python FastAPI)
- Runs a background CV pipeline that processes video frames
- Detects vehicles using YOLO11, tracks them with ByteTrack
- Analyzes lane congestion and calculates adaptive signal timing
- Publishes MJPEG video stream at `GET /api/stream`
- Publishes lane and signal telemetry over WebSocket at `WS /ws/telemetry`
- Exposes RESTful API for config updates and emergency triggering

**Frontend** (React + Vite + TypeScript)
- Dashboard consuming the MJPEG stream and WebSocket telemetry
- Real-time visualization of lane congestion, vehicle counts, and signal state
- UI for configuring lane polygons, adjusting signal parameters, and triggering emergency preemption

## Setup

### Backend

1. Create and activate virtual environment:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r backend/requirements.txt
   ```

2. Run backend:
   ```bash
   .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
   ```
   Backend will:
   - Load or generate `config/smartflow.json` (4 lanes N/E/S/W by default)
   - Auto-download YOLO11n weights to repo root as `yolo11n.pt` on first run
   - Start the CV pipeline processing `videos/traffic.mp4`
   - Listen on `http://localhost:8000`

### Frontend

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Set up environment (optional — defaults to `http://localhost:8000`):
   ```bash
   echo "VITE_API_BASE=http://localhost:8000" > .env
   ```

3. Run dev server:
   ```bash
   npm run dev
   ```
   Frontend will be at `http://localhost:5173`

## API Reference

| Endpoint | Method | Description | Request | Response |
|----------|--------|-------------|---------|----------|
| `/api/health` | GET | Pipeline health and frame stats | — | `{ status, error, frame_index, fps }` |
| `/api/state` | GET | Current signal state and lane metrics | — | `{ ready, frame_index, fps, lanes, signal, vehicle_count }` |
| `/api/config` | GET | Current configuration (lanes, signal params) | — | Full config object |
| `/api/config/lanes` | PUT | Update lane polygons and capacities | `{ lanes: [{ id, name, polygon, capacity }] }` | Updated config |
| `/api/emergency/trigger` | POST | Trigger emergency preemption on a lane | `{ lane_id }` | `{ ok, lane_id }` |
| `/api/emergency/clear` | POST | Clear emergency state | — | `{ ok }` |
| `/api/stream` | GET | MJPEG video stream (annotated) | — | MJPEG stream (multipart/x-mixed-replace) |
| `/ws/telemetry` | WebSocket | Real-time telemetry (lanes, signal, counts) | — | JSON frames: `{ frame_index, fps, lanes, signal, vehicle_count }` |

## Configuration

`config/smartflow.json` (auto-created on first startup) controls:
- **lanes**: Polygon geometry and capacity for each direction (N/E/S/W)
- **signal_params**: Green time tuning, emergency override duration, fairness weights
- **jpeg_quality**: Video stream quality (default 75)
- **source**: Video file path (default `videos/traffic.mp4`)

Edit this file or use `/api/config/lanes` PUT endpoint to adjust lane definitions.

## Notes

- **YOLO weights location**: The `yolo11n.pt` model is downloaded to the repo root on first backend startup. This is controlled by the process's working directory — if you run the backend from a different cwd, the model will be downloaded to that location instead. This is a known rough edge and can be addressed by pinning model paths in config if needed.
- **Video source**: Currently processes `videos/traffic.mp4`. Point to a different file by editing `config/smartflow.json` → `source` field or piping from a camera if your CV pipeline supports it.
- **Emergency preemption**: Can use either a roof-beacon color heuristic (built-in) or a fine-tuned emergency vehicle classification model (optional).

## Quick Start (All-in-One)

Run both backend and frontend together:
```bash
chmod +x run.sh
./run.sh
```

This starts the backend on port 8000 and frontend on port 5173. Press Ctrl+C to stop both gracefully.
