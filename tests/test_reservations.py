"""Acceptance tests A5 + A6: customer creation, reservation constraints."""

import pytest

from harness.contract import ContractViolation


from harness.contract import ContractViolation

def _create_customer(client, name="Alice", email="alice@example.com", phone=None):
    body = {"name": name, "email": email}
    if phone:
        body["phone"] = phone
    return client.post("/customers", json_body=body)


def _active_table(client, seats):
    for t in client.get("/tables").get_json():
        if t["seats"] >= seats:
            return t
    raise RuntimeError("no table with >= %d seats" % seats)


# --- A5: Customer creation ---

def test_create_customer(client):
    resp = _create_customer(client, "Alice", "alice@example.com", "555-1234")
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "Alice"
    assert body["email"] == "alice@example.com"
    assert body["phone"] == "555-1234"
    assert isinstance(body["id"], int)


def test_create_customer_duplicate_email(client):
    _create_customer(client, "Alice", "alice@example.com")
    resp = _create_customer(client, "Bob", "alice@example.com")
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_create_customer_missing_fields(client):
    # Contract-first harness rejects an invalid request before it reaches the app
    with pytest.raises(ContractViolation):
        client.post("/customers", json_body={"name": "Alice"})


def test_create_customer_phone_optional(client):
    resp = _create_customer(client, "NoPhone", "nophone@example.com")
    assert resp.status_code == 201
    assert resp.get_json()["phone"] is None


# --- A6: Reservation constraints ---

def _create_reservation(client, customer_id, table_id, time, party_size):
    return client.post("/reservations", json_body={
        "customer_id": customer_id,
        "dining_table_id": table_id,
        "reservation_time": time,
        "party_size": party_size,
    })


def test_valid_reservation(client):
    cust = _create_customer(client, "ResCust", "res@example.com").get_json()
    table = _active_table(client, 4)
    resp = _create_reservation(client, cust["id"], table["id"], "2026-12-01T19:00:00Z", 2)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["party_size"] == 2
    assert body["status"] == "CONFIRMED"
    assert body["customer_id"] == cust["id"]
    assert body["dining_table_id"] == table["id"]

    get_resp = client.get("/reservations/%d" % body["id"])
    assert get_resp.status_code == 200
    assert get_resp.get_json()["id"] == body["id"]


def test_reservation_party_too_large(client):
    cust = _create_customer(client, "BigParty", "big@example.com").get_json()
    table = _active_table(client, 2)  # smallest available table, seats=2
    resp = _create_reservation(client, cust["id"], table["id"], "2026-12-02T19:00:00Z", 5)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_reservation_duplicate_table_time(client):
    cust = _create_customer(client, "DupeRes", "dupe@example.com").get_json()
    table = _active_table(client, 4)
    _create_reservation(client, cust["id"], table["id"], "2026-12-03T19:00:00Z", 2)
    resp = _create_reservation(client, cust["id"], table["id"], "2026-12-03T19:00:00Z", 2)
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_reservation_invalid_table(client):
    cust = _create_customer(client, "BadTable", "badtable@example.com").get_json()
    resp = _create_reservation(client, cust["id"], 9999, "2026-12-04T19:00:00Z", 2)
    assert resp.status_code == 404


def test_reservation_invalid_customer(client):
    tables = client.get("/tables").get_json()
    resp = _create_reservation(client, 9999, tables[0]["id"], "2026-12-05T19:00:00Z", 2)
    assert resp.status_code == 404


def test_reservation_party_zero(client):
    # party_size 0 violates the contract minimum of 1 -> rejected at request time
    cust = _create_customer(client, "ZeroParty", "zero@example.com").get_json()
    table = _active_table(client, 4)
    with pytest.raises(ContractViolation):
        _create_reservation(client, cust["id"], table["id"], "2026-12-06T19:00:00Z", 0)


def test_get_reservation_not_found(client):
    resp = client.get("/reservations/999999")
    assert resp.status_code == 404
    assert "error" in resp.get_json()