#!/usr/bin/env bash
# Product 005: launch the Restaurant backend + MCP gateway (Unix).
# Resets the database, starts the Product 004 API on :5000, then the MCP
# gateway on :8000 (Streamable HTTP at /mcp, Swagger UI at /docs).
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python}

echo "[1/3] Resetting database..."
"$PY" harness/reset_db.py .

echo "[2/3] Starting Product 004 backend on http://127.0.0.1:5000"
"$PY" src/app.py &
BACKEND_PID=$!

echo "[3/3] Starting MCP gateway on http://127.0.0.1:8000/mcp"
OPENAPI_FILE="$(pwd)/openapi.yaml" API_BASE_URL="http://127.0.0.1:5000" \
    "$PY" -m mcp_gateway.server &
GATEWAY_PID=$!

trap 'kill $BACKEND_PID $GATEWAY_PID 2>/dev/null || true' EXIT
wait