"""Thin generic OpenAPI-to-MCP gateway server.

Loads the configured OpenAPI document, exposes every operation as an MCP Tool
via FastMCP's OpenAPIProvider (no per-operation code), serves the identical
document read-only for Swagger UI, and forwards every tool call to the
configured HTTP backend through httpx2.

The gateway never imports sqlite3, never opens the backend database, and never
calls Flask handler functions. All RESTaurant-specific rules live in the
Product 004 backend, not here.
"""

import logging
import os
import time

import httpx2
import uvicorn
import yaml
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from . import swagger
from .config import Config, load_config, load_openapi_file

logger = logging.getLogger("mcp_gateway")

DEFAULT_SERVER_NAME = "OpenAPI Gateway"


class _ToolLoggingMiddleware(Middleware):
    """Log each MCP tool call with tool name, elapsed time and error summary.

    Generic business-free observation: it records nothing about what the tool
    means and never logs secrets (payloads are not included).
    """

    def __init__(self, log_level=logging.INFO):
        self._level = log_level

    async def on_call_tool(self, context, call_next):
        params = getattr(context, "message", None)
        name = getattr(params, "name", None) or context.method or "tools/call"
        started = time.perf_counter()
        try:
            result = await call_next(context)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.log(
                self._level,
                "mcp_tool name=%s result=error elapsed_ms=%.1f error=%s",
                name,
                elapsed_ms,
                exc,
            )
            raise
        else:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.log(
                self._level,
                "mcp_tool name=%s result=success elapsed_ms=%.1f",
                name,
                elapsed_ms,
            )
            return result


def _make_client(base_url: str, timeout: float) -> httpx2.AsyncClient:
    """Build the httpx2 client the OpenAPI tools forward through.

    Event hooks add generic HTTP line logs (method, path, upstream status,
    elapsed time, error summary). No payloads are logged.
    """

    async def _on_request(request: httpx2.Request) -> None:
        logger.debug(
            "upstream %s %s",
            request.method,
            str(request.url),
        )

    async def _on_response(response: httpx2.Response) -> None:
        # httpx2 forbids reading .elapsed until the body is read or closed.
        # aread() consumes and caches the body so a later .json()/.text call
        # still works while letting us report timing here.
        await response.aread()
        logger.log(
            logging.INFO,
            "upstream %s %s -> status=%s elapsed_ms=%.1f",
            response.request.method,
            str(response.request.url),
            response.status_code,
            (response.elapsed.total_seconds() if response.elapsed else 0) * 1000,
        )

    return httpx2.AsyncClient(
        base_url=base_url,
        timeout=httpx2.Timeout(timeout),
        event_hooks={"request": [_on_request], "response": [_on_response]},
    )


def build_gateway(cfg: Config):
    """Return ``(app, mcp, client)`` wired up for the given config.

    Fails fast with a clear ValueError when the OpenAPI document is missing or
    invalid, before any MCP request can be served.
    """
    spec = load_openapi_file(cfg.openapi_file)

    spec_title = "OpenAPI Gateway"
    if isinstance(spec.get("info"), dict) and spec["info"].get("title"):
        spec_title = "%s (MCP Gateway)" % spec["info"]["title"]

    client = _make_client(cfg.api_base_url, cfg.api_timeout)
    mcp = FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name=spec_title,
    )
    mcp.add_middleware(_ToolLoggingMiddleware())

    app = mcp.http_app(path=cfg.mcp_path)

    def _serve_spec(_request):
        return FileResponse(
            cfg.openapi_file,
            media_type="application/yaml",
            headers={"Cache-Control": "no-store"},
        )

    app.router.routes.append(Route("/openapi.yaml", _serve_spec, methods=["GET"]))
    app.router.routes.append(
        Route("/docs", lambda _request: HTMLResponse(swagger.index_html()), methods=["GET"])
    )
    app.router.routes.append(
        Route("/docs/", lambda _request: HTMLResponse(swagger.index_html()), methods=["GET"])
    )
    app.mount(
        swagger.STATIC_PREFIX,
        StaticFiles(directory=swagger.static_dir()),
        name="swaggerui",
    )

    app.router.routes.append(
        Route(
            "/",
            lambda _request: PlainTextResponse(
                "OpenAPI-to-MCP gateway. MCP: %s | Swagger: /docs | Spec: /openapi.yaml\n"
                % cfg.mcp_url
            ),
            methods=["GET"],
        )
    )

    return app, mcp, client


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("mcp_gateway").setLevel(
        getattr(logging, cfg.log_level.upper(), logging.INFO)
    )

    app, _mcp, _client = build_gateway(cfg)

    logger.info("OpenAPI file: %s", cfg.openapi_file)
    logger.info("Upstream API base URL: %s", cfg.api_base_url)
    logger.info("MCP endpoint (Streamable HTTP): %s", cfg.mcp_url)
    logger.info("Swagger UI: %s", cfg.docs_url)

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()