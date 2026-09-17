"""Acceptance A1-A6: baseline, discovery, schema fidelity, swagger parity.

Exact discovery is the heart of Product 005: the MCP tool-set must equal the
approved OpenAPI operationId set, with input schemas derived from the contract
and no hand-written duplicate schemas anywhere.
"""

import json
import os
import re

import httpx2
import pytest

from mcp_gateway.tests.conftest import (
    EXPECTED_OPERATION_IDS,
    MCP_HOST,
    REPO_ROOT,
    SPEC_PATH,
    operation_ids,
)


def test_openapi_operation_ids_match_approved_set():
    ids = sorted(operation_ids())
    assert ids == sorted(EXPECTED_OPERATION_IDS), "%r != %r" % (ids, EXPECTED_OPERATION_IDS)


def test_mcp_tool_names_match_openapi_operation_ids(mcp_harness):
    tools = mcp_harness.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted(EXPECTED_OPERATION_IDS), "%r != %r" % (names, EXPECTED_OPERATION_IDS)


def test_no_extra_or_missing_tools(mcp_harness):
    names = mcp_harness.tool_names()
    assert set(names) == set(EXPECTED_OPERATION_IDS)
    assert len(names) == len(EXPECTED_OPERATION_IDS) == 10


def test_every_tool_has_description(mcp_harness):
    for tool in mcp_harness.list_tools():
        assert tool.description and tool.description.strip(), tool.name


def test_schema_fidelity_required_fields(mcp_harness):
    tools = {t.name: t for t in mcp_harness.list_tools()}

    create_customer = tools["createCustomer"]
    props = create_customer.input_schema.get("properties", {})
    assert create_customer.input_schema.get("required") == ["name", "email"]
    assert props["email"].get("format") == "email"
    assert "phone" in props and "phone" not in create_customer.input_schema.get("required", [])

    create_reservation = tools["createReservation"]
    assert sorted(create_reservation.input_schema.get("required", [])) == sorted(
        ["customer_id", "dining_table_id", "reservation_time", "party_size"]
    )
    assert create_reservation.input_schema["properties"]["party_size"].get("minimum") == 1

    update_status = tools["updateOrderStatus"]
    assert update_status.input_schema.get("required") == ["id", "status"]
    enum = update_status.input_schema["properties"]["status"].get("enum")
    assert enum == ["NEW", "PREPARING", "READY", "COMPLETED", "CANCELLED"]

    path_tools = ["getMenuItem", "getReservation", "getOrder", "listCustomerOrders"]
    for name in path_tools:
        assert tools[name].input_schema.get("required") == ["id"], name
        assert tools[name].input_schema["properties"]["id"].get("type") == "integer", name


def test_schema_fidelity_create_order_body(mcp_harness):
    tools = {t.name: t for t in mcp_harness.list_tools()}
    create_order = tools["createOrder"]
    params = create_order.input_schema
    properties = params["properties"]
    assert params.get("required") == ["items"]
    items = properties["items"]
    assert items.get("type") == "array"
    assert items.get("minItems") == 1
    assert sorted(items["items"].get("required", [])) == ["menu_item_id", "quantity"]
    assert items["items"]["properties"]["quantity"].get("minimum") == 1


GATEWAY_SOURCE_FILES = [
    "__init__.py",
    "config.py",
    "server.py",
    "swagger.py",
]


def _gateway_source_modules():
    pkg = os.path.join(REPO_ROOT, "mcp_gateway")
    for name in GATEWAY_SOURCE_FILES:
        with open(os.path.join(pkg, name), "r", encoding="utf-8") as f:
            yield name, f.read()


def test_no_handwritten_duplicate_schema_in_gateway_source():
    """A14 — the gateway may not contain a second, hand-maintained schema."""
    table = set(EXPECTED_OPERATION_IDS)
    for name, text in _gateway_source_modules():
        # Skip triple-quoted docstrings and comments; only inspect real code.
        code = re.sub(r'"""(?:.|\n)*?"""', "", text)
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        hits = table.intersection(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", code))
        assert not hits, "hand-written per-operation code found in %s: %s" % (name, sorted(hits))


def test_gateway_source_has_no_sqlite_and_no_flask_handler_imports():
    """A6 — the gateway talks HTTP only."""
    for name, text in _gateway_source_modules():
        assert "import sqlite3" not in text, (name, "imports sqlite3")
        assert "from sqlite3" not in text, (name, "imports from sqlite3")
        assert "sqlite3.connect" not in text, (name, "opens sqlite database")
        assert "from src" not in text and "from handlers" not in text, (name, "imports backend")
        assert "create_app" not in text, (name, "imports Flask app")


def test_swagger_ui_served_with_same_spec(gateway_session):
    """A5 — Swagger UI at /docs loads the exact same openapi.yaml."""
    base = "http://%s:%s" % (MCP_HOST, gateway_session["port"])

    docs = httpx2.get(base + "/docs", timeout=10)
    assert docs.status_code == 200
    html = docs.text
    assert 'id="swagger-ui"' in html
    assert "/openapi.yaml" in html

    spec_resp = httpx2.get(base + "/openapi.yaml", timeout=10)
    assert spec_resp.status_code == 200
    served = spec_resp.content
    with open(SPEC_PATH, "rb") as f:
        on_disk = f.read()
    assert served == on_disk, "/openapi.yaml must be the exact approved file"

    served_ids = operation_ids()
    assert sorted(served_ids) == sorted(EXPECTED_OPERATION_IDS)
    served_text = served.decode("utf-8", errors="replace")
    for operation_id in EXPECTED_OPERATION_IDS:
        assert operation_id in html or operation_id in served_text