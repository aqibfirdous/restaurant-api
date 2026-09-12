#!/usr/bin/env bash
# One-command clean test run for the Restaurant OpenAPI + SQLite harness.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python}

echo "[1/3] Validating OpenAPI contract..."
"$PY" harness/validate_openapi.py openapi.yaml

echo "[2/3] Resetting database..."
"$PY" harness/reset_db.py .

echo "[3/3] Running contract + business tests..."
"$PY" -m pytest tests -v

echo "ALL PASS"