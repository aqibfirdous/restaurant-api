"""Generic HTTP contract validation against an OpenAPI document.

This module is harness-only. It knows how to validate *any* request/response
against *any* OpenAPI document; it contains zero application business logic.
"""

import json
import os

import yaml
from werkzeug.datastructures import Headers
from werkzeug.datastructures import ImmutableMultiDict

try:
    from openapi_core import OpenAPI
    from openapi_core.datatypes import RequestParameters
except Exception as _exc:  # pragma: no cover - import guard
    OpenAPI = None
    RequestParameters = None
    _IMPORT_ERROR = _exc
else:
    _IMPORT_ERROR = None


class ContractViolation(AssertionError):
    """Raised when a request or response does not match the OpenAPI contract."""


def _format_errors(errors):
    seen, lines = set(), []
    for err in errors:
        text = str(err).strip().replace("\n", " ")
        if text not in seen:
            seen.add(text)
            lines.append(text)
    return "; ".join(lines)


def _to_bytes(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value).encode("utf-8")


def load_spec_dict(spec_path):
    with open(spec_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class HarnessRequest:
    """Minimal object satisfying openapi_core.protocols.Request."""

    def __init__(self, method, path, body=None, query=None, headers=None,
                 cookies=None, host_url="http://localhost/"):
        self._method = method
        self._path = path
        self._host_url = host_url
        self.body = _to_bytes(body)
        self.content_type = "application/json" if body is not None else "application/octet-stream"
        self.parameters = RequestParameters(
            query=ImmutableMultiDict(list((query or {}).items())),
            header=Headers(list((headers or {}).items())),
            cookie=ImmutableMultiDict(list((cookies or {}).items())),
        )

    @property
    def method(self):
        return self._method

    @property
    def path(self):
        return self._path

    @property
    def host_url(self):
        return self._host_url


class HarnessResponse:
    """Minimal object satisfying openapi_core.protocols.Response."""

    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self.data = _to_bytes(body)
        self.content_type = "application/json" if body is not None else "application/octet-stream"
        self.headers = Headers(list((headers or {}).items()))


class Contract:
    """Wraps an OpenAPI document and validates requests/responses."""

    def __init__(self, spec_path):
        if OpenAPI is None:
            raise RuntimeError("openapi-core is not available: %s" % _IMPORT_ERROR)
        self.spec_path = os.path.abspath(spec_path)
        self.spec_dict = load_spec_dict(self.spec_path)
        self.openapi = OpenAPI.from_dict(self.spec_dict)
        servers = self.spec_dict.get("servers") or []
        if servers:
            self.base_url = servers[0]["url"].rstrip("/") + "/"
        else:
            self.base_url = "http://localhost/"

    def _request(self, method, path, body=None, query=None, headers=None):
        return HarnessRequest(
            method.lower(),
            path,
            body=body,
            query=query,
            headers=headers,
            cookies=None,
            host_url=self.base_url,
        )

    def validate_request(self, method, path, body=None, query=None, headers=None):
        return list(self.openapi.iter_request_errors(
            self._request(method, path, body=body, query=query, headers=headers)
        ))

    def validate_response(self, method, path, status_code, body,
                          query=None, headers=None, cookies=None):
        request = self._request(method, path, query=query, headers=headers)
        response = HarnessResponse(status_code, body=body)
        return list(self.openapi.iter_response_errors(request, response))


class ContractClient:
    """HTTP test client that validates every request/response against the spec.

    It wraps a Flask test client (or any object exposing an ``open`` method)
    so tests exercise the HTTP interface, not handler functions.
    """

    def __init__(self, app, spec_path):
        self.contract = Contract(spec_path)
        self.client = app.test_client()

    def _checked(self, method, path, json_body=None, query=None, **kwargs):
        req_errors = self.contract.validate_request(
            method, path, body=json_body, query=query
        )
        if req_errors:
            raise ContractViolation(
                "Request for %s %s violates OpenAPI contract: %s"
                % (method.upper(), path, _format_errors(req_errors))
            )

        response = self.client.open(path, method=method, json=json_body,
                                    query_string=query or {}, **kwargs)
        body = response.get_json(silent=True)
        resp_errors = self.contract.validate_response(
            method, path, response.status_code, body, query=query
        )
        if resp_errors:
            raise ContractViolation(
                "Response for %s %s (%s) violates OpenAPI contract: %s"
                % (method.upper(), path, response.status_code, _format_errors(resp_errors))
            )
        return response

    def get(self, path, query=None, **kwargs):
        return self._checked("GET", path, query=query, **kwargs)

    def post(self, path, json_body=None, query=None, **kwargs):
        return self._checked("POST", path, json_body=json_body, query=query, **kwargs)

    def patch(self, path, json_body=None, query=None, **kwargs):
        return self._checked("PATCH", path, json_body=json_body, query=query, **kwargs)

    def delete(self, path, query=None, **kwargs):
        return self._checked("DELETE", path, query=query, **kwargs)