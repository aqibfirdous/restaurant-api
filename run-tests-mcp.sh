#!/usr/bin/env bash
# Product 005: one-command clean rerun of BOTH suites (Unix).
# Resets the database and runs the Product 004 harness, then the Product 005
# MCP gateway acceptance suite (which boots real backend + gateway subprocesses
# against fresh databases and free ports).
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python}

echo "[1/4] Validating OpenAPI contract..."
"$PY" harness/validate_openapi.py openapi.yaml

echo "[2/4] Resetting database..."
"$PY" harness/reset_db.py .

echo "[3/4] Product 004 harness..."
"$PY" -m pytest tests -q

echo "[4/4] Product 005 MCP gateway acceptance..."
"$PY" -m pytest mcp_gateway/tests -q

echo "ALL PASS"