"""Minimal Swagger UI integration on top of the FastMCP Starlette app.

The SOW requires Swagger UI and MCP to read the exact same approved
openapi.yaml. This module renders a stock Swagger UI page that loads the
gateway's read-only ``/openapi.yaml`` mount point; Swagger "Try It Out" then
calls the same Product 004 HTTP backend that the MCP tools forward to.
"""

import os

from flask_swagger_ui import __file__ as _flask_swagger_ui_file

FLASK_SWAGGER_UI_DIST = os.path.join(os.path.dirname(_flask_swagger_ui_file), "dist")

STATIC_PREFIX = "/swaggerui"
SPEC_URL_PATH = "/openapi.yaml"


def static_dir() -> str:
    """Directory holding the bundled Swagger UI assets (read-only, never edited)."""
    return FLASK_SWAGGER_UI_DIST


def index_html(title: str = "Restaurant API — Swagger UI") -> str:
    """Return the Swagger UI bootstrap page.

    The page loads the spec from ``/openapi.yaml`` on this same gateway, which
    is the identical file the MCP provider consumed at startup.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>%s</title>
  <link rel="stylesheet" type="text/css" href="%s/index.css">
  <link rel="stylesheet" type="text/css" href="%s/swagger-ui.css">
  <link rel="icon" type="image/png" href="%s/favicon-32x32.png" sizes="32x32">
  <link rel="icon" type="image/png" href="%s/favicon-16x16.png" sizes="16x16">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="%s/swagger-ui-bundle.js"></script>
  <script src="%s/swagger-ui-standalone-preset.js"></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: "%s",
        dom_id: "#swagger-ui",
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
        plugins: [SwaggerUIBundle.plugins.DownloadUrl],
        layout: "StandaloneLayout"
      });
    };
  </script>
</body>
</html>
""" % (
        title,
        STATIC_PREFIX,
        STATIC_PREFIX,
        STATIC_PREFIX,
        STATIC_PREFIX,
        STATIC_PREFIX,
        STATIC_PREFIX,
        SPEC_URL_PATH,
    )