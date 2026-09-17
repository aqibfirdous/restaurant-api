"""Acceptance A3/B1/B2/B3: failure handling through the gateway.

Verifies fail-fast startup on an invalid OpenAPI document, clear and
non-hanging failures when the upstream API is unreachable, argument-schema
enforcement at the MCP layer, and that business errors from the backend stay
readable across the gateway.
"""

import os
import uuid

import pytest

from mcp_gateway.tests.conftest import (
    MCPHarness,
    free_port,
    http_ok,
    start_gateway,
)


def test_gateway_refuses_to_start_with_invalid_openapi():
    """B1 — a broken/absent OpenAPI document fails at startup, not at request time."""
    bad = os.path.join(os.environ.get("TEMP", "."), "bad-openapi-%s.yaml" % uuid.uuid4().hex[:6])
    with open(bad, "w", encoding="utf-8") as f:
        f.write("paths: not-a-mapping:\n  x: [\n")
    try:
        with pytest.raises(RuntimeError) as exc:
            start_gateway(openapi_file=bad)
        assert "failed to start" in str(exc.value).lower()
    finally:
        if os.path.exists(bad):
            os.remove(bad)


def test_missing_openapi_file_fails_fast():
    missing = os.path.join(
        os.environ.get("TEMP", "."), "no-such-openapi-%s.yaml" % uuid.uuid4().hex[:6]
    )
    with pytest.raises(RuntimeError) as exc:
        start_gateway(openapi_file=missing)
    assert "failed to start" in str(exc.value).lower()


def test_backend_down_fails_fast_and_clearly():
    """A3/B3 — gateway runs; calls to a dead upstream fail fast, not hang."""
    dead_port = free_port()
    port, svc, log = start_gateway(api_base_url="http://127.0.0.1:%s/" % dead_port)
    harness = None
    try:
        harness = MCPHarness("http://127.0.0.1:%s/mcp" % port, log=log.append)
        ok, data = harness.call("listMenu")
        assert not ok, "expected failure when upstream is down"
        text = harness.error_text(data)
        assert "Error calling tool" in text, text
    finally:
        if harness is not None:
            harness.close()
        svc.stop()


def test_required_argument_enforced_locally(mcp_harness):
    """Missing required args are rejected at the MCP layer before any HTTP."""
    ok, data = mcp_harness.call("createCustomer", {"name": "No Email"})
    assert not ok, "missing required email must fail"
    text = mcp_harness.error_text(data)
    assert "email" in text.lower(), text


def test_business_error_preserved(mcp_harness):
    """Backend business errors surface with readable detail through MCP."""
    email = "failmode+%s@example.com" % uuid.uuid4().hex[:8]
    ok, data = mcp_harness.call("createCustomer", {"name": "Grace", "email": email})
    assert ok, mcp_harness.error_text(data)

    _ok2, dup = mcp_harness.call("createCustomer", {"name": "Grace Clone", "email": email})
    assert not _ok2
    text = mcp_harness.error_text(dup)
    assert "already exists" in text, text


def test_nonexistent_resource_404(mcp_harness):
    ok, data = mcp_harness.call("getReservation", {"id": 999999})
    assert not ok, "missing reservation must not succeed"
    text = mcp_harness.error_text(data)
    assert "404" in text or "not found" in text.lower(), text


def test_invalid_status_value_is_rejected(mcp_harness):
    """Out-of-state values are rejected with the backend's transition rule."""
    _ok, menu = mcp_harness.call("listMenu")
    assert _ok, mcp_harness.error_text(menu)
    items = [i for cat in menu["result"] for i in cat["items"]]

    email = "bogus+%s@example.com" % uuid.uuid4().hex[:8]
    _ok, customer = mcp_harness.call("createCustomer", {"name": "Bogus Test", "email": email})
    assert _ok, mcp_harness.error_text(customer)

    _ok, order = mcp_harness.call(
        "createOrder",
        {"customer_id": customer["id"], "items": [{"menu_item_id": items[0]["id"], "quantity": 1}]},
    )
    assert _ok, mcp_harness.error_text(order)

    ok, data = mcp_harness.call("updateOrderStatus", {"id": order["id"], "status": "BOGUS"})
    assert not ok, "out-of-schema status must be rejected"
    text = mcp_harness.error_text(data)
    assert "BOGUS" in text, text


def test_upstream_down_still_serves_swagger():
    """Gateway keeps serving docs/spec even when its upstream is unreachable."""
    port, svc, _log = start_gateway(api_base_url="http://127.0.0.1:1/")
    try:
        ok, _ = http_ok("http://127.0.0.1:%s/docs" % port)
        assert ok, "swagger UI must remain served when upstream is down"
        ok_spec, _ = http_ok("http://127.0.0.1:%s/openapi.yaml" % port)
        assert ok_spec
    finally:
        svc.stop()