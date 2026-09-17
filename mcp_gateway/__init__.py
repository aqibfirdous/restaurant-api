"""Generic OpenAPI-to-MCP gateway (Product 005 FRESHERS).

Loads one approved OpenAPI document, exposes every operation as an MCP Tool
through FastMCP's OpenAPIProvider, and forwards calls to the configured HTTP
backend. The same OpenAPI document also feeds the human-facing Swagger UI.
"""

__version__ = "0.1.0"