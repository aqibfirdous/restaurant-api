"""Acceptance A7-A11: canonical Restaurant workflow over MCP.

Runs the exact SOW dogfood sequence through MCP against a clean database:
list menu -> get item -> create customer -> duplicate email error -> list
tables -> reserve -> read reservation -> create order -> read order (server
total) -> state transitions -> invalid transition -> order history.
"""

import os
import time
import uuid

import pytest

from mcp_gateway.tests.conftest import (
    MCPHarness,
    SPEC_PATH,
    http_ok,
    start_backend,
    start_gateway,
)


def _result_list(ok, data):
    """Normalize a list-returning tool result to a list."""
    assert ok, MCPHarness.error_text(data)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    if isinstance(data, dict) and "content" in data:
        import json as _json

        try:
            return _json.loads(data["content"])
        except Exception:
            return data["content"]
    return data


def _result_dict(ok, data):
    assert ok, MCPHarness.error_text(data)
    return data


@pytest.fixture(scope="module")
def workflow_backend():
    url, svc = start_backend()
    yield {"url": url, "svc": svc}
    svc.stop()


@pytest.fixture(scope="module")
def workflow_gateway(workflow_backend):
    port, svc, log = start_gateway(api_base_url=workflow_backend["url"])
    yield {"url": "http://127.0.0.1:%s/mcp" % port, "port": port, "svc": svc, "log": log}
    svc.stop()


@pytest.fixture(scope="module")
def wf(workflow_gateway):
    """(harness, gateway) for a genuinely fresh backend + gateway pair."""
    harness = MCPHarness(workflow_gateway["url"], log=workflow_gateway["log"].append)
    yield harness, workflow_gateway
    harness.close()


def canonical_workflow(harness: MCPHarness, email_tag: str):
    """Run the SOW step 4-9 dogfood flow; return the collected pass checks."""
    stamp = "%s-%s" % (email_tag, uuid.uuid4().hex[:8])

    menu = _result_list(*harness.call("listMenu"))
    assert menu, "listMenu returned no categories"
    all_items = [item for cat in menu for item in cat["items"]]
    assert all_items, "listMenu returned no items"

    some_item = all_items[0]
    item = _result_dict(*harness.call("getMenuItem", {"id": some_item["id"]}))
    assert item["id"] == some_item["id"]

    email = "alice+%s@example.com" % stamp
    customer = _result_dict(*harness.call("createCustomer", {"name": "Alice", "email": email}))
    assert customer.get("email") == email
    customer_id = customer["id"]

    dup_ok, dup_data = harness.call("createCustomer", {"name": "Alice Again", "email": email})
    assert not dup_ok, "duplicate email must fail"
    assert "already exists" in harness.error_text(dup_data), harness.error_text(dup_data)

    tables = _result_list(*harness.call("listDiningTables"))
    assert tables, "listDiningTables returned no tables"
    table_id = tables[0]["id"]

    party = 2
    reserve_time = "2035-06-01T19:30:00"
    reservation = _result_dict(
        *harness.call(
            "createReservation",
            {
                "customer_id": customer_id,
                "dining_table_id": table_id,
                "reservation_time": reserve_time,
                "party_size": party,
            },
        )
    )
    assert reservation["customer_id"] == customer_id
    assert reservation["party_size"] == party
    reservation_id = reservation["id"]

    fetched_res = _result_dict(*harness.call("getReservation", {"id": reservation_id}))
    assert fetched_res["id"] == reservation_id

    two_items = all_items[:2]
    order = _result_dict(
        *harness.call(
            "createOrder",
            {
                "customer_id": customer_id,
                "dining_table_id": table_id,
                "reservation_id": reservation_id,
                "items": [
                    {"menu_item_id": two_items[0]["id"], "quantity": 2},
                    {"menu_item_id": two_items[1]["id"], "quantity": 1},
                ],
            },
        )
    )
    assert order["status"] == "NEW"

    expected = 2 * two_items[0]["price_cents"] + 1 * two_items[1]["price_cents"]
    assert order["total_cents"] == expected, "server-computed total mismatch"
    order_id = order["id"]

    fetched_order = _result_dict(*harness.call("getOrder", {"id": order_id}))
    assert fetched_order["total_cents"] == expected
    assert len(fetched_order["items"]) == 2

    final_status = "COMPLETED"
    for status in ("PREPARING", "READY", final_status):
        updated = _result_dict(*harness.call("updateOrderStatus", {"id": order_id, "status": status}))
        assert updated["status"] == status

    bad_ok, bad_data = harness.call("updateOrderStatus", {"id": order_id, "status": "NEW"})
    assert not bad_ok, "COMPLETED -> NEW must be rejected"
    assert "transition" in harness.error_text(bad_data).lower(), harness.error_text(bad_data)

    history = _result_list(*harness.call("listCustomerOrders", {"id": customer_id}))
    assert history, "order history must not be empty"
    completed = [o for o in history if o["id"] == order_id]
    assert completed, "completed order missing from history"
    assert completed[0]["status"] == final_status

    return {
        "customer_id": customer_id,
        "order_id": order_id,
        "expected_total": expected,
        "email": email,
    }


def test_canonical_user_workflow_from_readme(wf):
    """The SOW dogfood run: fresh DB + fresh gateway, full flow via MCP."""
    harness, gateway = wf
    checks = canonical_workflow(harness, "canonical")
    assert checks["expected_total"] > 0


def test_menu_and_customer_a7(wf):
    harness, _gateway = wf
    menu = _result_list(*harness.call("listMenu"))
    item = _result_dict(*harness.call("getMenuItem", {"id": menu[0]["items"][0]["id"]}))

    email = "bob+%s@example.com" % uuid.uuid4().hex[:8]
    customer = _result_dict(*harness.call("createCustomer", {"name": "Bob", "email": email}))
    assert customer["email"] == email

    ok, data = harness.call("createCustomer", {"name": "Bob Clone", "email": email})
    assert not ok
    assert "already exists" in harness.error_text(data)


def test_reservation_a8(wf):
    harness, _gateway = wf
    tables = _result_list(*harness.call("listDiningTables"))
    table_id = tables[0]["id"]

    email = "carol+%s@example.com" % uuid.uuid4().hex[:8]
    customer = _result_dict(*harness.call("createCustomer", {"name": "Carol", "email": email}))

    slot = "2035-07-0%sT20:00:00" % (uuid.uuid4().hex[:6].isdigit())
    reservation = _result_dict(
        *harness.call(
            "createReservation",
            {
                "customer_id": customer["id"],
                "dining_table_id": table_id,
                "reservation_time": slot,
                "party_size": 2,
            },
        )
    )
    got = _result_dict(*harness.call("getReservation", {"id": reservation["id"]}))
    assert got["id"] == reservation["id"]

    ok, _data = harness.call(
        "createReservation",
        {
            "customer_id": customer["id"],
            "dining_table_id": table_id,
            "reservation_time": slot,
            "party_size": 2,
        },
    )
    assert not ok, "duplicate table+time reservation must fail"

    seats = tables[0]["seats"]
    ok, data = harness.call(
        "createReservation",
        {
            "customer_id": customer["id"],
            "dining_table_id": table_id,
            "reservation_time": "2035-08-0%sT20:00:00" % uuid.uuid4().hex[:6],
            "party_size": seats + 1,
        },
    )
    assert not ok, "oversized party must fail"
    assert "capacity" in harness.error_text(data) or "exceeds" in harness.error_text(data)


def test_order_transaction_a9(wf):
    harness, _gateway = wf
    menu = _result_list(*harness.call("listMenu"))
    items = [item for cat in menu for item in cat["items"]]

    email = "dave+%s@example.com" % uuid.uuid4().hex[:8]
    customer = _result_dict(*harness.call("createCustomer", {"name": "Dave", "email": email}))

    order = _result_dict(
        *harness.call(
            "createOrder",
            {
                "customer_id": customer["id"],
                "items": [{"menu_item_id": items[0]["id"], "quantity": 3}],
            },
        )
    )
    expected = 3 * items[0]["price_cents"]
    assert order["total_cents"] == expected, "server owns prices/totals"

    fetched = _result_dict(*harness.call("getOrder", {"id": order["id"]}))
    assert fetched["total_cents"] == expected
    assert fetched["items"][0]["quantity"] == 3


def test_state_machine_a10(wf):
    harness, _gateway = wf
    menu = _result_list(*harness.call("listMenu"))
    item = [i for cat in menu for i in cat["items"]][0]

    email = "erin+%s@example.com" % uuid.uuid4().hex[:8]
    customer = _result_dict(*harness.call("createCustomer", {"name": "Erin", "email": email}))
    order = _result_dict(
        *harness.call(
            "createOrder",
            {"customer_id": customer["id"], "items": [{"menu_item_id": item["id"], "quantity": 1}]},
        )
    )
    assert order["status"] == "NEW"

    for status in ("PREPARING", "READY", "COMPLETED"):
        updated = _result_dict(*harness.call("updateOrderStatus", {"id": order["id"], "status": status}))
        assert updated["status"] == status

    ok, data = harness.call("updateOrderStatus", {"id": order["id"], "status": "PREPARING"})
    assert not ok
    assert "transition" in harness.error_text(data).lower()

    ok, data = harness.call("updateOrderStatus", {"id": order["id"], "status": "NEW"})
    assert not ok


def test_order_history_a11(wf):
    harness, _gateway = wf
    menu = _result_list(*harness.call("listMenu"))
    item = [i for cat in menu for i in cat["items"]][0]

    email = "frank+%s@example.com" % uuid.uuid4().hex[:8]
    customer = _result_dict(*harness.call("createCustomer", {"name": "Frank", "email": email}))
    order = _result_dict(
        *harness.call(
            "createOrder",
            {"customer_id": customer["id"], "items": [{"menu_item_id": item["id"], "quantity": 1}]},
        )
    )
    for status in ("PREPARING", "READY", "COMPLETED"):
        _result_dict(*harness.call("updateOrderStatus", {"id": order["id"], "status": status}))

    history = _result_list(*harness.call("listCustomerOrders", {"id": customer["id"]}))
    ids = [o["id"] for o in history]
    assert order["id"] in ids
    matching = [o for o in history if o["id"] == order["id"]]
    assert matching[0]["status"] == "COMPLETED"