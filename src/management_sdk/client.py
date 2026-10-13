"""Synchronous Apps HTTP client, with no Runtime protocol or local SDK access."""
import http.client
import json
import math
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Optional


class ManagementError(Exception):
    """Typed Apps/server or transport failure. No mutation is automatically retried."""
    def __init__(self, message: str, *, code: str, http_status: Optional[int] = None,
                 request_id: Optional[str] = None, details: Any = None,
                 response: Any = None, outcome_unknown: bool = False):
        super().__init__(message)
        self.code, self.http_status, self.request_id = code, http_status, request_id
        self.details = {} if details is None else details
        self.response, self.outcome_unknown = response, outcome_unknown

    def __str__(self):
        return f"{self.code}: {super().__str__()} (HTTP {self.http_status}, request {self.request_id})"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ManagementClient:
    """Connect to Apps, which selects the single running application.

    Session/context and CSRF are internal. Create a new client after a session
    change and explicitly decide new commands; old commands are never replayed.
    Instances are synchronous and intended for sequential calls.
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8080", *, timeout: float = 10.0):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("base_url must be an http(s) Apps origin without credentials or a path")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number of seconds")
        self.base_url, self.timeout = base_url.rstrip("/"), timeout
        self._csrf = None
        self._context = None
        self._last_request_id = None
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, path: str, body=None, *, current: bool = True, bootstrap: bool = False):
        mutating = body is not None and path != "parameters/read"
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        if not bootstrap and current and (self._csrf is None or self._context is None):
            session = self._request("session", current=False, bootstrap=True)
            if not isinstance(session, dict) or not isinstance(session.get("csrf_token"), str) or not session["csrf_token"] or (session.get("context") is not None and not isinstance(session["context"], str)):
                raise ManagementError("Invalid Apps management session", code="SDK_PROTOCOL", http_status=200,
                                      request_id=self._last_request_id, response=session)
            self._csrf, self._context = session["csrf_token"], session.get("context")
        identity = "sdk-" + uuid.uuid4().hex
        self._last_request_id = identity
        headers = {"Accept": "application/json", "X-Request-ID": identity}
        if self._context is not None:
            headers["X-Management-Context"] = self._context
        if data is not None:
            headers.update({"Content-Type": "application/json", "X-CSRF-Token": self._csrf,
                            "Origin": self.base_url, "Sec-Fetch-Site": "same-origin"})
        request = urllib.request.Request(self.base_url + "/api/v1/management/" + path, data=data, headers=headers)
        status = None
        try:
            try:
                response = self._opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.code
                raw = response.read()
        except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
            cause = getattr(error, "reason", error)
            code = "SDK_TIMEOUT" if isinstance(cause, (TimeoutError, socket.timeout)) else "SDK_TRANSPORT"
            raise ManagementError(str(error), code=code, http_status=status, request_id=identity,
                                  details={"path": path}, outcome_unknown=mutating) from error
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise ManagementError("Apps returned invalid JSON", code="SDK_PROTOCOL", http_status=status,
                                  request_id=identity, outcome_unknown=mutating) from error
        if not isinstance(value, dict) or value.get("schema_version") != 1 or type(value.get("ok")) is not bool:
            raise ManagementError("Invalid Apps response", code="SDK_PROTOCOL", http_status=status,
                                  request_id=identity, response=value, outcome_unknown=mutating)
        if not value["ok"] or not 200 <= status < 300:
            error = value.get("error") or {}
            if not isinstance(error, dict):
                raise ManagementError("Invalid Apps error envelope", code="SDK_PROTOCOL", http_status=status,
                                      request_id=identity, response=value, outcome_unknown=mutating)
            details = error.get("details", {})
            raise ManagementError(error.get("message", "Apps rejected request"), code=error.get("code", "SDK_PROTOCOL"),
                                  http_status=status, request_id=identity, details=details, response=value,
                                  outcome_unknown=mutating and (status >= 500 or error.get("code") in ("RD_UNREACHABLE", "RD_ENVELOPE", "MG_OUTCOME_UNKNOWN")))
        if value.get("request_id") != identity:
            raise ManagementError("Apps response request ID mismatch", code="SDK_PROTOCOL", http_status=status,
                                  request_id=identity, response=value, outcome_unknown=mutating)
        if "result" not in value:
            raise ManagementError("Apps response has no result", code="SDK_PROTOCOL", http_status=status,
                                  request_id=identity, response=value, outcome_unknown=mutating)
        return value["result"]

    def list_block_types(self) -> list:
        return self._request("types", current=False)

    def get_block_type(self, name: str) -> dict:
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a nonempty name from list_block_types()")
        return self._request("types/" + urllib.parse.quote(name, safe=""), current=False)

    def list_instances(self) -> list:
        return self._request("instances")

    def get_connections(self) -> list:
        return self._request("connections")

    def get_status(self) -> dict:
        return self._request("status")

    def create_connection(self, source: str, destination: str) -> dict:
        return self._request("connections/create", {"source": source, "destination": destination})

    def delete_connection(self, source: str, destination: str) -> dict:
        return self._request("connections/delete", {"source": source, "destination": destination})

    def read_parameter(self, reference: str) -> Any:
        return self._request("parameters/read", {"reference": reference})

    def write_parameter(self, reference: str, value: Any) -> dict:
        return self._request("parameters/write", {"reference": reference, "value": value})

    def trigger_event(self, reference: str) -> dict:
        return self._request("events/trigger", {"reference": reference})
