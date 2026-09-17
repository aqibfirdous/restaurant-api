@echo off
rem Product 005: one-command clean rerun of BOTH suites (Windows).
rem Resets the database and runs the Product 004 harness, then the Product 005
rem MCP gateway acceptance suite (which boot real backend + gateway subprocesses
rem against fresh databases and free ports).
cd /d %~dp0

echo [1/4] Validating OpenAPI contract...
.venv\Scripts\python.exe harness\validate_openapi.py openapi.yaml || exit /b 1

echo [2/4] Resetting database...
.venv\Scripts\python.exe harness\reset_db.py . || exit /b 1

echo [3/4] Product 004 harness...
.venv\Scripts\python.exe -m pytest tests -q || exit /b 1

echo [4/4] Product 005 MCP gateway acceptance...
.venv\Scripts\python.exe -m pytest mcp_gateway\tests -q || exit /b 1

echo ALL PASS