"""Environment-driven configuration for the MCP gateway.

Nothing here is hard-coded to a specific API. Point the gateway at a different
peer by changing only the environment variables below.

Variables:
    OPENAPI_FILE   Path to the approved OpenAPI document (source of truth).
    API_BASE_URL   Base URL of the Product 004 HTTP API the gateway forwards to.
    MCP_HOST       Host to bind the Streamable HTTP endpoint (default 127.0.0.1).
    MCP_PORT       Port to bind (default 8000).
    MCP_PATH       MCP endpoint path (default /mcp).
    API_TIMEOUT    Upstream request timeout in seconds (default 30).
    GATEWAY_LOG_LEVEL  Logging level for the gateway (default INFO).
"""

import os
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class Config:
    openapi_file: str
    api_base_url: str
    host: str
    port: int
    mcp_path: str
    api_timeout: float
    log_level: str

    @property
    def mcp_url(self) -> str:
        return "http://%s:%s%s" % (self.host, self.port, self.mcp_path)

    @property
    def docs_url(self) -> str:
        return "http://%s:%s/docs" % (self.host, self.port)

    @property
    def demo_url(self) -> str:
        return "%s/demo" % self.api_base_url


def _default_openapi_file() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "openapi.yaml")


def load_config(env=None) -> Config:
    """Build a Config from ``env`` (defaults to os.environ)."""
    env = os.environ if env is None else env
    return Config(
        openapi_file=env.get("OPENAPI_FILE", _default_openapi_file()),
        api_base_url=env.get("API_BASE_URL", "http://127.0.0.1:5000").rstrip("/"),
        host=env.get("MCP_HOST", "127.0.0.1"),
        port=int(env.get("MCP_PORT", "8000")),
        mcp_path=env.get("MCP_PATH", "/mcp") or "/mcp",
        api_timeout=float(env.get("API_TIMEOUT", "30")),
        log_level=env.get("GATEWAY_LOG_LEVEL", "INFO"),
    )


def load_openapi_file(path: str) -> dict:
    """Load and minimally validate the configured OpenAPI document.

    Raises a clear ValueError (fail fast) on a missing file, YAML parse
    failure, or a document that is not a usable OpenAPI spec. No second schema
    is created anywhere: the result is used directly by the MCP provider and
    served untouched to Swagger UI.
    """
    if not path or not os.path.exists(path):
        raise ValueError("OPENAPI_FILE not found: %s" % (path or "<unset>"))

    try:
        with open(path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as exc:
        raise ValueError("Cannot parse OpenAPI document %s: %s" % (path, exc))

    if not isinstance(spec, dict):
        raise ValueError("OpenAPI document %s does not parse to an object" % path)
    if "openapi" not in spec:
        raise ValueError("OpenAPI document %s is missing the 'openapi' version key" % path)
    if not isinstance(spec.get("paths"), dict) or not spec["paths"]:
        raise ValueError("OpenAPI document %s must declare a non-empty 'paths' map" % path)

    return spec