"""Generic OpenAPI specification validation.

This module is harness-only. It contains no application business logic.
"""

import os

import yaml
from openapi_spec_validator import validate as validate_spec


def load_spec(spec_path):
    with open(spec_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_openapi(spec_path):
    """Return (is_valid: bool, errors: list[str]).

    Verifies the YAML parses and the document is a valid OpenAPI 3.x spec.
    """
    if not os.path.exists(spec_path):
        return False, ["Spec file not found: %s" % spec_path]
    try:
        spec_dict = load_spec(spec_path)
    except Exception as exc:
        return False, ["YAML parse error: %s" % exc]

    if not isinstance(spec_dict, dict) or "openapi" not in spec_dict:
        return False, ["Document does not look like an OpenAPI spec (missing 'openapi' key)"]

    try:
        validate_spec(spec_dict)
        return True, []
    except Exception as exc:
        return False, ["OpenAPI validation error: %s" % exc]


if __name__ == "__main__":
    import sys

    ok, errors = validate_openapi(sys.argv[1] if len(sys.argv) > 1 else "openapi.yaml")
    if ok:
        print("OPENAPI VALID")
    else:
        print("OPENAPI INVALID")
        for e in errors:
            print(" -", e)
        sys.exit(1)