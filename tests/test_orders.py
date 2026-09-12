"""Acceptance tests A7, A8, A9, A10: order transactions and state machine."""

import pytest

from harness.contract import ContractViolation
from src import db


def _all_menu_items(client):
    items = []
    for category in client.get("/menu").get_json():
        items.extend(category["items"])
    return items


def _create_customer(client, email):
    resp = client.post("/customers", json_body={"name": "Buyer", "email": email})
    assert resp.status_code == 201
    return resp.get_json()


def _create_order(client, customer_id, items, customer_extra=None):
    body = {"customer_id": customer_id, "items": items}
    if customer_extra:
        body.update(customer_extra)
    return client.post("/orders", json_body=body)


def _new_order(client, email):
    customer = _create_customer(client, email)
    item = _all_menu_items(client)[0]
    resp = _create_order(client, customer["id"], [{"menu_item_id": item["id"], "quantity": 1}])
    assert resp.status_code == 201
    return customer, item, resp.get_json()


# --- A7: Order transaction; server owns prices/totals ---

def test_create_order_prices_and_total_from_database(client):
    customer = _create_customer(client, "prices@example.com")
    first = _all_menu_items(client)[0]
    second = _all_menu_items(client)[1]

    # Client attempts to supply its own price -> must be ignored
    resp = _create_order(client, customer["id"], [
        {"menu_item_id": first["id"], "quantity": 2, "unit_price_cents": 1},
        {"menu_item_id": second["id"], "quantity": 1, "unit_price_cents": 1},
    ])
    assert resp.status_code == 201
    body = resp.get_json()

    expected_total = first["price_cents"] * 2 + second["price_cents"]
    assert body["total_cents"] == expected_total
    assert body["status"] == "NEW"

    unit = {oi["menu_item_id"]: oi for oi in body["items"]}
    assert unit[first["id"]]["unit_price_cents"] == first["price_cents"]
    assert unit[first["id"]]["quantity"] == 2
    assert unit[first["id"]]["line_total_cents"] == first["price_cents"] * 2
    assert unit[second["id"]]["unit_price_cents"] == second["price_cents"]


def test_create_order_unavailable_item_rejected(client):
    customer = _create_customer(client, "unavail@example.com")
    con = db.connect()
    row = con.execute("SELECT id FROM menu_items WHERE available = 0 LIMIT 1").fetchone()
    con.close()
    assert row is not None, "seed must contain an unavailable menu item"

    resp = _create_order(client, customer["id"], [{"menu_item_id": row["id"], "quantity": 1}])
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_create_order_missing_menu_item_rejected(client):
    customer = _create_customer(client, "missing@example.com")
    resp = _create_order(client, customer["id"], [{"menu_item_id": 999999, "quantity": 1}])
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_create_order_empty_items_rejected(client):
    # minItems: 1 in the contract -> rejected at request time by the harness
    customer = _create_customer(client, "empty@example.com")
    with pytest.raises(ContractViolation):
        _create_order(client, customer["id"], [])


def test_create_order_unknown_customer_rejected(client):
    item = _all_menu_items(client)[0]
    resp = client.post("/orders", json_body={
        "customer_id": 999999,
        "items": [{"menu_item_id": item["id"], "quantity": 1}],
    })
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_order_items_written_together(client):
    customer = _create_customer(client, "together@example.com")
    item = _all_menu_items(client)[0]
    resp = _create_order(client, customer["id"], [{"menu_item_id": item["id"], "quantity": 3}])
    assert resp.status_code == 201
    con = db.connect()
    rows = con.execute("SELECT * FROM order_items WHERE order_id = ?", (resp.get_json()["id"],)).fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0]["quantity"] == 3


# --- A8: getOrder returns joined order ---

def test_get_order(client):
    customer, item, order = _new_order(client, "getorder@example.com")
    resp = client.get("/orders/%d" % order["id"])
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == order["id"]
    assert body["status"] == "NEW"
    assert body["total_cents"] == item["price_cents"]
    assert isinstance(body["created_at"], str)
    assert len(body["items"]) == 1
    assert body["items"][0]["menu_item_id"] == item["id"]
    assert body["items"][0]["unit_price_cents"] == item["price_cents"]


def test_get_order_not_found(client):
    resp = client.get("/orders/999999")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


# --- A9: Status state machine ---

def test_allowed_status_transitions(client):
    customer, _, order = _new_order(client, "transitions@example.com")
    order_id = order["id"]
    sequence = ["PREPARING", "READY", "COMPLETED"]
    for new_status in sequence:
        resp = client.patch("/orders/%d/status" % order_id, json_body={"status": new_status})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == new_status


def test_invalid_transition_new_to_completed(client):
    customer, _, order = _new_order(client, "badtrans@example.com")
    resp = client.patch("/orders/%d/status" % order["id"], json_body={"status": "COMPLETED"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_invalid_transition_skipping_state(client):
    customer, _, order = _new_order(client, "skip@example.com")
    order_id = order["id"]
    assert client.patch("/orders/%d/status" % order_id, json_body={"status": "PREPARING"}).status_code == 200
    # PREPARING can only go to READY, not COMPLETED
    resp = client.patch("/orders/%d/status" % order_id, json_body={"status": "COMPLETED"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_cancel_new_order(client):
    customer, _, order = _new_order(client, "cancel@example.com")
    resp = client.patch("/orders/%d/status" % order["id"], json_body={"status": "CANCELLED"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "CANCELLED"
    # terminal: cannot move on
    resp2 = client.patch("/orders/%d/status" % order["id"], json_body={"status": "NEW"})
    assert resp2.status_code == 400


def test_update_status_not_found(client):
    resp = client.patch("/orders/999999/status", json_body={"status": "PREPARING"})
    assert resp.status_code == 404


# --- A10: Customer order history ---

def test_list_customer_orders(client):
    customer, item, order = _new_order(client, "history@example.com")
    resp = client.get("/customers/%d/orders" % customer["id"])
    assert resp.status_code == 200
    history = resp.get_json()
    assert any(o["id"] == order["id"] for o in history)


def test_list_customer_orders_unknown_customer(client):
    resp = client.get("/customers/999999/orders")
    assert resp.status_code == 404
    assert "error" in resp.get_json()