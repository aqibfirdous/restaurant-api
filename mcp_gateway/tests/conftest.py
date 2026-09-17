"""Shared fixtures for the Product 005 acceptance suite.

The suite is black-box: it starts the real Product 004 Flask backend and the
real MCP gateway as subprocesses on free ports, then talks to the gateway over
Streamable HTTP with a real FastMCP client. Nothing is imported from the
backend handlers and no SQLite access happens here.
"""

import asyncio
import os
import socket
import subprocess
import sys
import threading
import time

import pytest
import yaml
from fastmcp import Client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

SPEC_PATH = os.path.join(REPO_ROOT, "openapi.yaml")
SCHEMA_PATH = os.path.join(REPO_ROOT, "schema.sql")
SEED_PATH = os.path.join(REPO_ROOT, "seed.sql")

EXPECTED_OPERATION_IDS = [
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

MCP_HOST = "127.0.0.1"


def operation_ids(spec_path=None) -> list[str]:
    with open(spec_path or SPEC_PATH, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    ids = []
    for path_item in spec["paths"].values():
        for method, op in path_item.items():
            if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                if op.get("operationId"):
                    ids.append(op["operationId"])
    return ids


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((MCP_HOST, 0))
        return s.getsockname()[1]


def _wait_for(ready_fn, timeout=45.0, interval=0.25, label="service"):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        ok, last = ready_fn()
        if ok:
            return
        time.sleep(interval)
    raise RuntimeError("%s did not become ready: %s" % (label, last))


def http_ok(url: str):
    import httpx2 as httpx

    try:
        r = httpx.get(url, timeout=2.0)
        return r.status_code < 500, "GET %s -> %s" % (url, r.status_code)
    except Exception as exc:  # noqa: BLE001 - readiness probing
        return False, "GET %s -> %s" % (url, exc)


class MCPHarness:
    """A FastMCP client living on a dedicated background event loop.

    Methods are synchronous for pytest; each call is scheduled onto the loop
    with ``run_coroutine_threadsafe`` and blocks on the result.
    """

    def __init__(self, url: str, log=None):
        self._url = url
        self._log = log or (lambda *_: None)
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._client = None
        self._error = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="mcp-harness")
        self._thread.start()
        if not self._ready.wait(60):
            raise RuntimeError("MCP client failed to connect: %s" % self._error)

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._task = self._loop.create_task(self._holder())
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.close()
            finally:
                pass

    async def _holder(self):
        try:
            async with Client(self._url) as client:
                self._client = client
                self._ready.set()
                while not self._stop.is_set():
                    await asyncio.sleep(0.25)
        except Exception as exc:  # noqa: BLE001
            self._error = exc
            self._ready.set()

    def _submit(self, coro, timeout=90):
        if self._client is None:
            raise RuntimeError("MCP client not connected: %s" % self._error)
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def list_tools(self):
        return self._submit(self._client.list_tools())

    def tool_names(self) -> list[str]:
        return sorted(t.name for t in self.list_tools())

    def call(self, name: str, arguments=None):
        """Call a tool and return (ok: bool, data).

        A non-zero/error tool result is returned as ok=False with the error
        payload; the helper never raises for upstream business or HTTP errors
        so tests can assert on them. Transport-level failures (backend down)
        are returned ok=False too.
        """
        arguments = dict(arguments or {})
        self._log("mcp.call %s %r" % (name, arguments))
        try:
            result = self._submit(self._client.call_tool(name, arguments))
        except Exception as exc:  # connection / protocol failures
            self._log("mcp.call %s raised: %s" % (name, exc))
            return False, {"error": str(exc), "_raised": True}
        self._log("mcp.call %s result=%r" % (name, result))
        ok = not getattr(result, "isError", False)
        return ok, self._to_dict(result)

    @staticmethod
    def _to_dict(result):
        data = getattr(result, "structured_content", None)
        if data is not None:
            return data
        content = getattr(result, "content", None)
        if isinstance(content, list):
            parts = [getattr(item, "text", None) for item in content]
            parts = [p for p in parts if p is not None]
            if parts:
                return {"content": "\n".join(parts)}
        if isinstance(content, (str, bytes)):
            return {"content": content.decode() if isinstance(content, bytes) else content}
        return {"content": content}

    @staticmethod
    def error_text(data) -> str:
        if isinstance(data, dict):
            return str(data.get("content") or data.get("error") or data)
        return str(data)

    def close(self):
        self._stop.set()

        async def _shutdown():
            task = getattr(self, "_task", None)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            try:
                self._loop.stop()
            except RuntimeError:  # pragma: no cover
                pass

        try:
            asyncio.run_coroutine_threadsafe(_shutdown(), self._loop).result(timeout=10)
        except Exception:  # noqa: BLE001 - loop already gone or wedged
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except RuntimeError:  # pragma: no cover
                pass
        self._thread.join(timeout=10)


class ServerProcess:
    def __init__(self, cmd, env, cwd):
        self.output = ""
        self.proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._reader = threading.Thread(target=self._pump, daemon=True, name="out-pump")
        self._reader.start()

    def _pump(self):
        try:
            for line in self.proc.stdout:
                self.output += line
        except Exception:  # noqa: BLE001
            pass

    def drain(self):
        return self.output

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=8)
        self.drain()
        return self.output


def _base_env(paths: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONUNBUFFERED"] = "1"
    for key in ("OPENAPI_FILE", "API_BASE_URL", "RESTAURANT_DB", "HOST", "PORT"):
        env.pop(key, None)
    if paths:
        env.update(paths)
    return env


def start_backend(db_path=None):
    """Start a fresh Product 004 backend and return (url, ServerProcess)."""
    import tempfile

    from harness.reset_db import reset_db

    if db_path is None:
        tmp = tempfile.mkdtemp(prefix="p005-backend-")
        db_path = os.path.join(tmp, "restaurant.db")
    reset_db(db_path, SCHEMA_PATH, SEED_PATH)

    port = free_port()
    env = _base_env({"RESTAURANT_DB": db_path, "HOST": MCP_HOST, "PORT": str(port)})
    svc = ServerProcess([sys.executable, "src/app.py"], env=env, cwd=REPO_ROOT)

    url = "http://%s:%s/" % (MCP_HOST, port)

    def ready():
        if svc.proc.poll() is not None:
            raise RuntimeError("backend process exited (code %s)" % svc.proc.returncode)
        return http_ok(url)

    try:
        _wait_for(ready, timeout=45, label="backend")
    except Exception:
        raise RuntimeError(
            "Backend failed to start.\n--- backend output ---\n%s" % svc.stop()
        )
    return url.rstrip("/"), svc


def start_gateway(openapi_file=None, api_base_url=None, mcp_path="/mcp"):
    """Start a gateway and return (mcp_port, ServerProcess, log list)."""
    port = free_port()
    log = []
    env = _base_env(
        {
            "OPENAPI_FILE": openapi_file or SPEC_PATH,
            "API_BASE_URL": api_base_url or "http://127.0.0.1:5001",
            "MCP_HOST": MCP_HOST,
            "MCP_PORT": str(port),
            "MCP_PATH": mcp_path,
            "GATEWAY_LOG_LEVEL": "INFO",
        }
    )
    svc = ServerProcess([sys.executable, "-m", "mcp_gateway.server"], env=env, cwd=REPO_ROOT)

    def ready():
        if svc.proc.poll() is not None:
            raise RuntimeError("gateway process exited (code %s)" % svc.proc.returncode)
        return http_ok("http://%s:%s/" % (MCP_HOST, port))

    try:
        _wait_for(ready, timeout=45, label="gateway")
    except Exception:
        raise RuntimeError(
            "Gateway failed to start.\n--- gateway output ---\n%s" % svc.stop()
        )
    return port, svc, log


@pytest.fixture(scope="session")
def backend_session():
    """Product 004 backend on a clean database for the whole suite."""
    url, svc = start_backend()
    yield {"url": url, "svc": svc}
    svc.stop()


@pytest.fixture(scope="session")
def gateway_session(backend_session):
    """One shared stateless gateway whose upstream is the session backend."""
    port, svc, log = start_gateway(api_base_url=backend_session["url"])
    yield {"url": "http://%s:%s/mcp" % (MCP_HOST, port), "port": port, "svc": svc, "log": log}
    svc.stop()


@pytest.fixture(scope="session")
def mcp_harness(gateway_session):
    """A real FastMCP client connected to the session gateway over HTTP."""
    harness = MCPHarness(gateway_session["url"], log=gateway_session["log"].append)
    yield harness
    harness.close()