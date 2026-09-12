"""Harness acceptance tests: A1, A2, A3, A11, A12, A13.

These tests verify the *harness* itself, not the restaurant business rules
(which live in test_menu.py, test_reservations.py, test_orders.py).
"""

import os
import sqlite3

import pytest

from harness.contract import Contract
from harness.reset_db import reset_db
from harness.validate_openapi import validate_openapi

HERO_COLUMNS = (
    "customers", "dining_tables", "reservations",
    "menu_items", "orders", "order_items",
)

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")
SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed.sql")
SPEC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.yaml")
HARNESS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness")


# --- A1: OpenAPI validity ---

def test_openapi_is_valid():
    ok, errors = validate_openapi(SPEC)
    assert ok, errors


# --- A2: Deterministic clean database from schema + seed ---

def _dump(db_path):
    con = sqlite3.connect(db_path)
    out = []
    try:
        for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            rows = con.execute("SELECT * FROM %s ORDER BY rowid" % table).fetchall()
            out.append((table, [tuple(r) for r in rows]))
    finally:
        con.close()
    return out


def test_clean_db_recreated_deterministically(tmp_path):
    a = str(tmp_path / "a.db")
    b = str(tmp_path / "b.db")
    reset_db(a, SCHEMA, SEED)
    reset_db(b, SCHEMA, SEED)
    assert _dump(a) == _dump(b)
    assert os.path.exists(a)
    # and both are actually usable, with seeded content
    con = sqlite3.connect(a)
    count = con.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
    con.close()
    assert count > 0


# --- A3: Contract judge catches wrong responses ---

def test_contract_judge_catches_wrong_body_shape():
    contract = Contract(SPEC)
    errors = contract.validate_response("GET", "/menu", 200, {"not": "an array"})
    assert errors, "harness must reject a wrong response body"


def test_contract_judge_catches_wrong_status_code():
    contract = Contract(SPEC)
    errors = contract.validate_response("GET", "/menu", 418, [])
    assert errors, "harness must reject an undefined status code"


def test_contract_judge_catches_schema_violation():
    contract = Contract(SPEC)
    errors = contract.validate_response("GET", "/menu/1", 200, {"id": 1})
    assert errors, "harness must reject a response missing required fields"


def test_contract_judge_accepts_valid_response():
    contract = Contract(SPEC)
    errors = contract.validate_response("GET", "/menu", 200, [])
    assert not errors


# --- A11: Repeatable fresh-DB runs ---

def test_workflow_runs_from_fresh_db_twice():
    import tempfile
    from harness.contract import ContractClient
    from src.app import create_app

    def run_once():
        workdir = tempfile.mkdtemp()
        db = reset_db(os.path.join(workdir, "db.sqlite"), SCHEMA, SEED)
        old = os.environ.get("RESTAURANT_DB")
        os.environ["RESTAURANT_DB"] = db
        try:
            client = ContractClient(create_app(), SPEC)
            cust = client.post("/customers", json_body={"name": "Repeat", "email": "repeat@example.com"})
            assert cust.status_code == 201
            menu = client.get("/menu").get_json()
            item = menu[0]["items"][0]
            order = client.post("/orders", json_body={
                "customer_id": cust.get_json()["id"],
                "items": [{"menu_item_id": item["id"], "quantity": 1}],
            })
            assert order.status_code == 201
            assert order.get_json()["total_cents"] == item["price_cents"]
        finally:
            if old is None:
                os.environ.pop("RESTAURANT_DB", None)
            else:
                os.environ["RESTAURANT_DB"] = old
            os.remove(db)

    run_once()
    run_once()


# --- A12: Harness contains no restaurant-specific logic ---

@pytest.mark.parametrize("token", [
    "menu", "reservation", "party_size", "price_cents",
    "dining_table", "customer", "restaurant",
])
def test_harness_has_no_restaurant_logic(token):
    for filename in ("validate_openapi.py", "reset_db.py", "contract.py"):
        with open(os.path.join(HARNESS_DIR, filename), "r", encoding="utf-8") as f:
            assert token not in f.read().lower(), "%s contains restaurant token %r" % (filename, token)


# --- A13: Canonical fresher user test, end to end ---

def test_dogfood_canonical_workflow(client):
    # 1. GET /menu
    menu = client.get("/menu")
    assert menu.status_code == 200
    menu_data = menu.get_json()
    assert menu_data

    # 2. POST /customers - create Alice
    alice = client.post("/customers", json_body={
        "name": "Alice",
        "email": "alice@dogfood.example",
        "phone": "555-0000",
    })
    assert alice.status_code == 201
    customer = alice.get_json()

    # 3. GET /tables - choose a 4-seat table
    tables = client.get("/tables")
    assert tables.status_code == 200
    table = next(t for t in tables.get_json() if t["seats"] >= 4)

    # 4. POST /reservations - Alice, party of 2
    reservation = client.post("/reservations", json_body={
        "customer_id": customer["id"],
        "dining_table_id": table["id"],
        "reservation_time": "2026-12-10T19:00:00Z",
        "party_size": 2,
    })
    assert reservation.status_code == 201
    reservation_id = reservation.get_json()["id"]

    # 5. POST /orders - Alice orders 2 menu items
    items = [item for cat in menu_data for item in cat["items"]][:2]
    order = client.post("/orders", json_body={
        "customer_id": customer["id"],
        "dining_table_id": table["id"],
        "reservation_id": reservation_id,
        "items": [{"menu_item_id": m["id"], "quantity": 1} for m in items],
    })
    assert order.status_code == 201
    order_id = order.get_json()["id"]

    # 6. GET /orders/{id} - verify server total
    fetched = client.get("/orders/%d" % order_id)
    assert fetched.status_code == 200
    assert fetched.get_json()["total_cents"] == sum(m["price_cents"] for m in items)

    # 7. PATCH NEW -> PREPARING -> READY -> COMPLETED
    for status in ("PREPARING", "READY", "COMPLETED"):
        resp = client.patch("/orders/%d/status" % order_id, json_body={"status": status})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == status

    # 8. GET /customers/{id}/orders - verify completed order
    history = client.get("/customers/%d/orders" % customer["id"])
    assert history.status_code == 200
    assert any(o["id"] == order_id and o["status"] == "COMPLETED" for o in history.get_json())