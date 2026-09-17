# Restaurant API — OpenAPI + SQLite Interface Harness

A simple, reusable development Harness for OpenAPI-first HTTP interfaces backed
by SQLite. It ships with a canonical **Restaurant** backend used to prove the
Harness works.

```
openapi.yaml  = CONTRACT / SOURCE OF TRUTH
      |
Fresher implements handlers + SQLite access
      |
Harness validates spec + resets DB + runs API + checks request/response contracts
      |
PASS = implementation matches OpenAPI + business rules
```

The **Harness** (`harness/`) is generic and reusable: swap in a new
`openapi.yaml`, `schema.sql`, `seed.sql` and `tests/` and it will validate and
drive that backend too.

---

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows
# or:  source .venv/bin/activate && pip install -r requirements.txt
```

## Reset the database

Creates `restaurant.db` from `schema.sql` + `seed.sql`:

```
python harness/reset_db.py .
```

The database file is disposable; every test run rebuilds it from scratch in a
temporary directory.

## Run the service

```
set RESTAURANT_DB=restaurant.db
.venv\Scripts\python src/app.py
```

The API listens on `http://127.0.0.1:5000`.

## Run the tests (one command)

```
run-tests.bat       # Windows
./run-tests.sh      # Linux/macOS
make test           # if make is available
```

Each run:
1. validates `openapi.yaml`,
2. resets a clean SQLite database,
3. runs the contract + business tests over the real HTTP interface,
4. prints PASS/FAIL per test and the failing `operationId`.

## Inspect the API

The contract is `openapi.yaml`. Every request into and every response out of
the service is validated against it by the Harness (`harness/contract.py`).

Quick manual checks:

```
curl http://127.0.0.1:5000/menu
curl http://127.0.0.1:5000/tables
curl -X POST http://127.0.0.1:5000/customers ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Alice\",\"email\":\"alice@example.com\"}"
```

## Canonical user test

From a clean database:

1. `GET /menu`
2. `POST /customers` — create Alice
3. `GET /tables` — choose a 4-seat table
4. `POST /reservations` — Alice, party of 2
5. `POST /orders` — Alice orders 2 menu items
6. `GET /orders/{id}` — verify the server-computed total (prices always come
   from SQLite, never from the client)
7. `PATCH /orders/{id}/status` NEW → PREPARING → READY → COMPLETED
8. `GET /customers/{id}/orders` — verify the completed order
9. Run `run-tests.bat` — everything PASSes

## Repository layout

```
restaurant-api/
  openapi.yaml        contract (source of truth)
  schema.sql          SQLite schema
  seed.sql            seed data
  src/
    app.py            Flask app + routes
    db.py             sqlite3 helpers
    handlers.py       the 10 operations + business rules
  harness/            << REUSABLE, zero restaurant logic >>
    validate_openapi.py
    reset_db.py
    contract.py       HTTP contract validation + test client
  tests/
    conftest.py
    test_menu.py
    test_reservations.py
    test_orders.py
    test_harness.py
  mcp_gateway/        << Product 005: generic OpenAPI-to-MCP gateway >>
    config.py         env-only configuration
    server.py         FastMCP.from_openapi + httpx2 forwarding + Swagger UI
    swagger.py        Swagger UI asset serving
    tests/            discovery, workflow, failures, cross-fresher suites
  requirements.txt
  run-tests.sh / run-tests.bat / Makefile
  run-mcp.sh / run-mcp.bat
  run-tests-mcp.sh / run-tests-mcp.bat
```

---

# Product 005 — Generic OpenAPI-to-MCP Gateway

`mcp_gateway/` publishes the **same** `openapi.yaml` two ways:

- **Swagger UI** (humans) at `http://127.0.0.1:8000/docs`
- **MCP Streamable HTTP** (AI agents) at `http://127.0.0.1:8000/mcp`
- **Live demo** (clickable restaurant flow) at `http://127.0.0.1:8000/demo`
  (redirects to the Product 004 page at `http://127.0.0.1:5000/demo`)

Every operation in the document becomes an MCP tool with the `operationId` as
its name. The gateway contains **zero per-endpoint code**: FastMCP's
OpenAPIProvider generates the tools directly from the spec, and every tool call
is forwarded over HTTP (via `httpx2`) to the Product 004 backend. There is no
SQLite access and no Flask-handler import anywhere in `mcp_gateway/`.

```
openapi.yaml (source of truth)
        |
        +---> Swagger UI (/docs)
        +---> Live demo   (/demo -> backend /demo)
        +---> FastMCP.from_openapi(openapi_spec, client)  -> tools/call
                                       |  httpx2
                                       v
                          Product 004 Flask backend (:5000)
```

### Run the gateway (Windows / Unix / Make)

```
run-mcp.bat            # or ./run-mcp.sh      (reset DB, backend :5000, gateway :8000)
make run-mcp
```

### Configuration (env only)

| Variable          | Default                        | Meaning                          |
|-------------------|--------------------------------|----------------------------------|
| `OPENAPI_FILE`    | repo `openapi.yaml`            | Contract loaded + served as-is   |
| `API_BASE_URL`    | `http://127.0.0.1:5000`        | Upstream HTTP backend            |
| `MCP_HOST`        | `127.0.0.1`                    | Bind host                        |
| `MCP_PORT`        | `8000`                         | Bind port                        |
| `MCP_PATH`        | `/mcp`                         | Streamable HTTP endpoint         |
| `API_TIMEOUT`     | `30`                           | Upstream timeout (seconds)       |
| `GATEWAY_LOG_LEVEL` | `INFO`                       | Gateway logging level            |

Errors are never hidden: HTTP errors from upstream surface through the MCP
error channel with status + body (e.g. `HTTP error 409: Conflict - {...}`), and
an unreachable backend fails fast with a clear message instead of hanging.

### Run both suites (one command)

```
run-tests-mcp.bat     # or ./run-tests-mcp.sh      (Product 004 + Product 005)
make test-mcp
```

### Canonical user test through MCP

From a clean database, with `openapi.yaml` served identically at `/docs` and as
MCP tools:

1. `listMenu` — see the menu, pick items
2. `createCustomer` — create Alice
3. `listDiningTables` — choose a 4-seat table
4. `createReservation` — Alice, party of 2
5. `createOrder` — Alice orders 2 menu items
6. `getOrder` — server-computed total (prices come from SQLite, never the client)
7. `updateOrderStatus` NEW → PREPARING → READY → COMPLETED
8. `listCustomerOrders` — verify the completed order
9. Trigger one expected business error (duplicate email) and confirm the error
   text is readable
10. Run `run-tests-mcp.bat` — both suites PASS

This sequence is captured verbatim in
`mcp_gateway/tests/test_workflow.py::test_canonical_user_workflow_from_readme`.

### Add a new endpoint

1. Add the path + schemas to `openapi.yaml` (the operationId names the test).
2. Add the table/inserts to `schema.sql` / `seed.sql` if backed by data.
3. Add a route + handler in `src/app.py` / `src/handlers.py`.
4. Add tests that call the route through `client` (`tests/conftest.py`), which
   auto-validates every request/response against the contract.
5. Run `run-tests.bat`.

The Harness itself never changes for a new backend model.