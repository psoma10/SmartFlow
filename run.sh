#!/bin/bash
set -euo pipefail

# SmartFlow 2.0: Start backend (uvicorn) and frontend (Vite) dev servers.
# Press Ctrl+C to stop both gracefully.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Verify required files exist
if [[ ! -f "$REPO_ROOT/backend/requirements.txt" ]]; then
  echo "Error: backend/requirements.txt not found"
  exit 1
fi

if [[ ! -f "$REPO_ROOT/frontend/package.json" ]]; then
  echo "Error: frontend/package.json not found"
  exit 1
fi

# Track child process PIDs
BACKEND_PID=""
FRONTEND_PID=""

# Cleanup function: kill child processes on exit
cleanup() {
  local exit_code=$?
  echo ""
  echo "Shutting down..."

  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" || true
    wait "$FRONTEND_PID" 2>/dev/null || true
  fi

  echo "Done."
  exit $exit_code
}

# Set trap for SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM EXIT

# Start backend
echo "Starting backend on http://localhost:$BACKEND_PORT..."
(
  cd "$REPO_ROOT"
  if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install -q -r backend/requirements.txt
  fi
  .venv/bin/uvicorn app.main:app \
    --app-dir backend \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --log-level info
) &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# Start frontend
echo "Starting frontend on http://localhost:$FRONTEND_PORT..."
(
  cd "$REPO_ROOT/frontend"
  if [[ ! -d "node_modules" ]]; then
    echo "Installing npm dependencies..."
    npm install -q
  fi
  npm run dev
) &
FRONTEND_PID=$!

# Print URLs
echo ""
echo "======================================"
echo "SmartFlow 2.0 is running!"
echo "======================================"
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "------------------------------------"
echo "Press Ctrl+C to stop both servers"
echo "======================================"
echo ""

# Wait for child processes
wait
