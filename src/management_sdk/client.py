"""Synchronous runtime-api/1 client; no command retries or local runtime access."""
import base64
import json
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional


class ManagementError(Exception):
    """Server, transport or protocol failure with the original outcome evidence.

    code is the server code when one exists, otherwise an SDK_* code.
    response retains the complete decoded envelope, including nested Operations.
    A transport failure on a mutation has outcome_unknown=True: do not resend.
    """

    def __init__(self, message: str, *, code: str, http_status: Optional[int] = None,
                 request_id: Optional[str] = None, details: Any = None,
                 response: Any = None, outcome_unknown: bool = False):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.request_id = request_id
        self.details = {} if details is None else details
        self.response = response
        self.outcome_unknown = outcome_unknown

    def __str__(self):
        return f"{self.code}: {super().__str__()} (HTTP {self.http_status}, request {self.request_id})"


def _identifier(value: str, label: str, limit: int = 128) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value) or len(value) > limit:
        raise ValueError(f"{label} must be a nonempty Runtime identifier (maximum {limit} characters)")
    return value


def _segment(value: str) -> str:
    return urllib.parse.quote(_identifier(value, "id"), safe="")


class ManagementClient:
    """An HTTP client bound to its first observed Runtime session.

    Application and connection deployment identities are always explicit.
    Create a new client after RD017, re-query identities and decide new commands.
    Instances are synchronous and intended for sequential use.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:18080", *,
                 token: Optional[str] = None, timeout: float = 10.0):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("base_url must be an http(s) server URL without credentials, query or fragment")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number of seconds")
        if token is not None and (not isinstance(token, str) or "\n" in token or "\r" in token):
            raise ValueError("token must be a single-line string")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = token
        self.session_id: Optional[str] = None
        # Do not route local Runtime requests through an ambient HTTP proxy.
        # Refuse redirects to avoid forwarding credentials or replaying commands.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    @staticmethod
    def new_request_id() -> str:
        """Allocate an ID before a command when timeout reconciliation is needed."""
        return "sdk-" + uuid.uuid4().hex

    def _ensure_session(self):
        if self.session_id is None:
            self.capabilities()

    def _request(self, method: str, path: str, body: Optional[Dict] = None, *,
                 request_id: Optional[str] = None, bootstrap: bool = False) -> Dict:
        request_id = self.new_request_id() if request_id is None else request_id
        if not bootstrap:
            self._ensure_session()
        mutating = method != "GET" and body is not None and body.get("Action") in ("CREATE", "DELETE", "WRITE")
        data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token is not None:
            headers["Authorization"] = "Bearer " + self.token
        if self.session_id is not None:
            headers["X-Runtime-Session"] = self.session_id
        if request_id:
            headers["X-Request-ID"] = request_id
        request = urllib.request.Request(self.base_url + "/api/v1/" + path, data=data, headers=headers, method=method)
        status = None
        try:
            try:
                response = self._opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.code
                raw = response.read()
        except (OSError, urllib.error.URLError) as error:
            cause = getattr(error, "reason", error)
            timed_out = isinstance(cause, (TimeoutError, socket.timeout))
            raise ManagementError(str(error), code="SDK_TIMEOUT" if timed_out else "SDK_TRANSPORT",
                                  http_status=status, request_id=request_id,
                                  details={"method": method, "path": path}, outcome_unknown=mutating) from error
        try:
            envelope = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise ManagementError("Runtime returned invalid JSON", code="SDK_PROTOCOL", http_status=status,
                                  request_id=request_id, details={"body": raw.decode("utf-8", errors="replace")},
                                  outcome_unknown=mutating) from error
        if not isinstance(envelope, dict) or envelope.get("api") != "runtime-api/1" or envelope.get("schema_version") != 1 or type(envelope.get("ok")) is not bool:
            raise ManagementError("Invalid runtime-api/1 envelope", code="SDK_PROTOCOL", http_status=status,
                                  request_id=request_id, response=envelope, outcome_unknown=mutating)
        def fail(error, fallback):
            error = error if isinstance(error, dict) else {}
            raise ManagementError(error.get("message", fallback), code=error.get("code", "SDK_PROTOCOL"),
                                  http_status=status, request_id=request_id,
                                  details=error.get("details", {}), response=envelope)
        if not envelope["ok"]:
            fail(envelope.get("error"), "Runtime rejected request")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise ManagementError("Runtime result must be an object", code="SDK_PROTOCOL", http_status=status,
                                  request_id=request_id, response=envelope, outcome_unknown=mutating)
        operation = result.get("operation")
        if operation is not None:
            if not isinstance(operation, dict):
                fail(None, "Invalid Operation record")
            if operation.get("state") != "succeeded":
                error = operation.get("error") or {"code": "SDK_OPERATION_INCOMPLETE", "message": "Operation has not succeeded", "details": {"state": operation.get("state"), "operation_id": operation.get("operation_id")}}
                fail(error, "Operation failed")
        if not 200 <= status < 300:
            fail(envelope.get("error"), "Unexpected HTTP status")
        if body is not None and "ID" in body and result.get("ID") != body["ID"]:
            raise ManagementError("Management response ID does not match command", code="SDK_PROTOCOL",
                                  http_status=status, request_id=request_id, response=envelope, outcome_unknown=mutating)
        if result.get("accepted") is False:
            raise ManagementError("Event was refused", code=result.get("code", "SDK_EVENT_REJECTED"),
                                  http_status=status, request_id=request_id, details=result, response=envelope)
        return result

    def capabilities(self) -> Dict:
        """Get capabilities and pin the session; a later change is reported."""
        identity = self.new_request_id()
        result = self._request("GET", "runtime/capabilities", bootstrap=True, request_id=identity)
        session = result.get("runtime_session_id")
        if not isinstance(session, str) or not session:
            raise ManagementError("Capabilities lacks runtime_session_id", code="SDK_PROTOCOL", http_status=200,
                                  request_id=identity, details=result)
        if self.session_id is not None and session != self.session_id:
            raise ManagementError("Runtime session changed", code="RD017", http_status=200,
                                  request_id=identity,
                                  details={"previous_session_id": self.session_id, "runtime_session_id": session})
        self.session_id = session
        return result

    def list_applications(self) -> Dict:
        return self._request("GET", "applications")

    def get_application(self, application_id: str) -> Dict:
        """Definition includes compiled function_blocks/ports and declared inputs."""
        return self._request("GET", "applications/" + _segment(application_id))

    def list_connection_deployments(self) -> Dict:
        return self._request("GET", "connection-deployments")

    def get_connection_deployment(self, connection_deployment_id: str) -> Dict:
        return self._request("GET", "connection-deployments/" + _segment(connection_deployment_id))

    def get_status(self, application_id: str, *, container: Optional[str] = None) -> Dict:
        path = "applications/" + _segment(application_id) + "/status"
        if container is not None:
            path += "?" + urllib.parse.urlencode({"container": _identifier(container, "container", 31)})
        return self._request("GET", path)

    def get_execution_state(self, application_id: str, *, since: Optional[str] = None) -> Dict:
        """Live topology/revision and bounded event admission/execution evidence."""
        path = "applications/" + _segment(application_id) + "/execution-state"
        if since is not None:
            path += "?" + urllib.parse.urlencode({"since": since})
        return self._request("GET", path)

    def get_request_result(self, request_id: str) -> Dict:
        """Connection result, including complete/result/error; no command replay."""
        return self._request("GET", "requests/" + _segment(request_id), request_id=request_id)

    def get_operation(self, operation_id: str) -> Dict:
        """Return the Operation's current state/result/error for explicit inspection."""
        return self._request("GET", "operations/" + _segment(operation_id))

    def _command(self, application_id: str, action: str, obj: Dict, *,
                 container: Optional[str] = None, request_id: Optional[str] = None, **fields) -> Dict:
        identity = self.new_request_id() if request_id is None else _identifier(request_id, "request_id")
        body = {"ID": identity, "Action": action, **obj, **fields}
        if action in ("CREATE", "DELETE") or (action == "WRITE" and "Parameter" in obj):
            body["request_id"] = identity
        if container is not None:
            body["DST"] = _identifier(container, "container", 31)
        return self._request("POST", "applications/" + _segment(application_id) + "/management", body, request_id=identity)

    def query_function_blocks(self, application_id: str, *, name: str = "*", fb_type: str = "*", container: Optional[str] = None) -> Dict:
        return self._command(application_id, "QUERY", {"FB": {"Name": name, "Type": fb_type}}, container=container)

    def query_parameters(self, application_id: str, reference: str = "*", *, container: Optional[str] = None) -> Dict:
        """Wildcard queries require an explicitly selected owning container."""
        if reference == "*" and container is None:
            raise ValueError("container is required for a wildcard parameter query")
        return self._command(application_id, "QUERY", {"Parameter": {"Reference": reference}}, container=container)

    def query_connections(self, application_id: str, connection_deployment_id: str, *, source: str = "*", destination: str = "*", container: Optional[str] = None) -> Dict:
        return self._command(application_id, "QUERY", {"Connection": {"Source": source, "Destination": destination}},
                             container=container, connection_deployment_id=_identifier(connection_deployment_id, "connection_deployment_id", 64))

    def _connection(self, action: str, application_id: str, connection_deployment_id: str, source: str, destination: str, *,
                    connection_type: str = "Event", expected_revision: Optional[int] = None,
                    container: Optional[str] = None, request_id: Optional[str] = None) -> Dict:
        if connection_type not in ("Event", "Data"):
            raise ValueError("connection_type must be Event or Data")
        _identifier(application_id, "application_id")
        _identifier(connection_deployment_id, "connection_deployment_id", 64)
        if expected_revision is None:
            # Read a confirmed revision from this exact application/deployment.
            expected_revision = self.query_connections(application_id, connection_deployment_id)["revision"]
        if type(expected_revision) is not int or not 0 <= expected_revision <= 2**64 - 1:
            raise ValueError("expected_revision must be a uint64 integer")
        return self._command(application_id, action, {"Connection": {"Source": source, "Destination": destination, "Type": connection_type}},
                             container=container, request_id=request_id, connection_deployment_id=connection_deployment_id, expected_revision=expected_revision)

    def create_connection(self, application_id: str, connection_deployment_id: str, source: str, destination: str, **options) -> Dict:
        """Synchronously add an edge between existing compiled instances/ports."""
        return self._connection("CREATE", application_id, connection_deployment_id, source, destination, **options)

    def delete_connection(self, application_id: str, connection_deployment_id: str, source: str, destination: str, **options) -> Dict:
        """Synchronously remove an edge; returns actual saved receipts/revision."""
        return self._connection("DELETE", application_id, connection_deployment_id, source, destination, **options)

    def read_parameter(self, application_id: str, reference: str, *, container: Optional[str] = None) -> Dict:
        return self._command(application_id, "READ", {"Parameter": {"Reference": reference}}, container=container)

    def write_parameter(self, application_id: str, reference: str, value: Any, *, container: Optional[str] = None, request_id: Optional[str] = None) -> Dict:
        """Assign typed JSON storage, check the nested Operation, do not fire events."""
        return self._command(application_id, "WRITE", {"Parameter": {"Reference": reference, "Value": value}}, container=container, request_id=request_id)

    def trigger_event(self, application_id: str, destination: str, *, container: Optional[str] = None,
                      payload: Optional[bytes] = None, request_id: Optional[str] = None) -> Dict:
        """Return admission only; optional bytes payload is a platform ABI extension."""
        connection = {"Source": "$e", "Destination": destination}
        if payload is not None:
            if not isinstance(payload, bytes):
                raise TypeError("payload must be bytes or None")
            connection["payload_base64"] = base64.b64encode(payload).decode("ascii")
        return self._command(application_id, "WRITE", {"Connection": connection}, container=container, request_id=request_id)
