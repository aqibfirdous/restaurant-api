@echo off
rem Product 005: launch the Restaurant backend + MCP gateway (Windows).
rem Resets the database, starts the Product 004 API on :5000, then the MCP
rem gateway on :8000 (Streamable HTTP at /mcp, Swagger UI at /docs).
cd /d %~dp0

echo [1/3] Resetting database...
.venv\Scripts\python.exe harness\reset_db.py . || exit /b 1

echo [2/3] Starting Product 004 backend on http://127.0.0.1:5000
start "restaurant-api backend" .venv\Scripts\python.exe src\app.py

echo [3/3] Starting MCP gateway on http://127.0.0.1:8000/mcp
set "OPENAPI_FILE=%~dp0openapi.yaml"
set "API_BASE_URL=http://127.0.0.1:5000"
start "mcp gateway" .venv\Scripts\python.exe -m mcp_gateway.server

echo Done.  Backend http://127.0.0.1:5000/  |  Swagger UI http://127.0.0.1:8000/docs  |  Spec http://127.0.0.1:8000/openapi.yaml