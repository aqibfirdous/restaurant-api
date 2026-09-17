"""Acceptance A15: the gateway is generic and isolation is real.

Two proofs:
  * Fresher behaviour — a fresh backend (new database) plus fresh gateway
    behaves identically: exactly the approved tools, clean menu, no leakage.
  * Spec-driven genericity — a *different* OpenAPI document (only the menu
    operations) exposed against the same live backend yields exactly that
    spec's tools and nothing else. The gateway serves what the document
    declares; it is not hard-wired to the Restaurant contract.
"""

import os
import uuid

from mcp_gateway.tests.conftest import (
    MCPHarness,
    SPEC_PATH,
    start_backend,
    start_gateway,
)


MINI_PATH = "/menu"
MINI_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Mini Menu API", "version": "0.1.0"},
    "paths": {
        "/menu": {
            "get": {
                "operationId": "listMenu",
                "summary": "List the menu",
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {"application/json": {"schema": {"type": "array"}}},
                    }
                },
            }
        }
    },
}
MINI_TOP = "/single"


def _write_mini_spec(tmpdir) -> str:
    import yaml

    path = os.path.join(tmpdir, "mini-openapi-%s.yaml" % uuid.uuid4().hex[:6])
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(MINI_SPEC, f)
    return path


def test_fresher_runs_full_suite_with_fresh_state():
    """A fresh DB + fresh gateway must show exactly the approved contract."""
    backend, gsvc = None, None
    harness = None
    try:
        backend_url, backend = start_backend()
        port, gsvc, log = start_gateway(api_base_url=backend_url)
        harness = MCPHarness("http://127.0.0.1:%s/mcp" % port, log=log.append)

        names = harness.tool_names()
        assert names == sorted(
            [
                "listMenu",
                "getMenuItem",
                "createCustomer",
                "listDiningTables",
                "createReservation",
                "getReservation",
                "createOrder",
                "getOrder",
                "updateOrderStatus",
                "listCustomerOrders",
            ]
        ), names

        ok, menu = harness.call("listMenu")
        assert ok, harness.error_text(menu)
        items = [i for cat in menu["result"] for i in cat["items"]]
        assert items and any(i["available"] for i in items)

        email = "fresher+%s@example.com" % uuid.uuid4().hex[:8]
        _ok, customer = harness.call("createCustomer", {"name": "Fresher", "email": email})
        assert _ok, harness.error_text(customer)

        ok, history = harness.call("listCustomerOrders", {"id": customer["id"]})
        assert ok, harness.error_text(history)
        assert history["result"] == [], "fresh database must start with no orders"
    finally:
        if harness is not None:
            harness.close()
        if gsvc is not None:
            gsvc.stop()
        if backend is not None:
            backend.stop()


def test_gateway_exposes_what_the_document_declares():
    """Genericity: the toolset tracks the loaded document, not the backend."""
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="p005-mini-")
    spec_file = _write_mini_spec(tmpdir)

    backend_url, backend = start_backend()
    gsvc = None
    harness = None
    try:
        port, gsvc, log = start_gateway(
            openapi_file=spec_file, api_base_url=backend_url
        )
        harness = MCPHarness("http://127.0.0.1:%s/mcp" % port, log=log.append)

        assert harness.tool_names() == ["listMenu"], harness.tool_names()

        ok, menu = harness.call("listMenu")
        assert ok, harness.error_text(menu)
        assert menu["result"]
    finally:
        if harness is not None:
            harness.close()
        if gsvc is not None:
            gsvc.stop()
        backend.stop()
        if os.path.exists(spec_file):
            os.remove(spec_file)


def test_spec_file_is_the_same_served_to_swagger(gateway_session):
    """The doc served at /openapi.yaml is byte-for-byte the approved spec."""
    import urllib.request

    from mcp_gateway.tests.conftest import http_ok

    base = gateway_session["url"].rsplit("/mcp", 1)[0]
    ok_flag, status = http_ok(base + "/openapi.yaml")
    assert ok_flag, status

    with open(SPEC_PATH, "rb") as f:
        local = f.read()
    with urllib.request.urlopen(base + "/openapi.yaml", timeout=5) as resp:
        served = resp.read()
    assert served == local
    assert served.startswith(b"openapi:")


def test_demo_redirects_to_backend_demo(gateway_session):
    """/demo on the gateway jumps to the live demo on the Product 004 backend."""
    import urllib.request

    base = gateway_session["url"].rsplit("/mcp", 1)[0]

    class NoFollow(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoFollow())
    try:
        with opener.open(base + "/demo", timeout=5) as resp:
            assert resp.status in (301, 302, 303, 307, 308)
            location = resp.headers.get("Location", "")
            assert location.endswith("/demo")
    except urllib.error.HTTPError as exc:
        assert exc.code in (301, 302, 303, 307, 308)
        assert exc.headers.get("Location", "").endswith("/demo")