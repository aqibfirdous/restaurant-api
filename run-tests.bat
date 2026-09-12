@echo off
rem One-command clean test run for the Restaurant OpenAPI + SQLite harness (Windows).
cd /d %~dp0

echo [1/3] Validating OpenAPI contract...
.venv\Scripts\python.exe harness\validate_openapi.py openapi.yaml || exit /b 1

echo [2/3] Resetting database...
.venv\Scripts\python.exe harness\reset_db.py . || exit /b 1

echo [3/3] Running contract + business tests...
.venv\Scripts\python.exe -m pytest tests -v || exit /b 1

echo ALL PASS