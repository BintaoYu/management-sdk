"""Offline tests use a loopback HTTP server, never a real Runtime."""
import base64
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from management_sdk import ManagementClient, ManagementError


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.session = "session-one"
        self.reply = lambda method, path, body: (200, {"ID": body["ID"]} if body else {})
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.loads(data) if data else None
                owner.calls.append((self.command, self.path, body, dict(self.headers)))
                if self.path == "/api/v1/runtime/capabilities":
                    status, result = 200, {"runtime_session_id": owner.session}
                else:
                    status, result = owner.reply(self.command, self.path, body)
                if isinstance(result, bytes):
                    raw = result
                else:
                    envelope = {"schema_version": 1, "api": "runtime-api/1", "ok": status < 400}
                    envelope["result" if status < 400 else "error"] = result
                    raw = json.dumps(envelope).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            do_GET = handle_request
            do_POST = handle_request

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ManagementClient(f"http://127.0.0.1:{self.server.server_port}", token="third-party", timeout=1)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def error(self, call, code, status):
        with self.assertRaises(ManagementError) as caught:
            call()
        self.assertEqual((caught.exception.code, caught.exception.http_status), (code, status))
        return caught.exception

    def test_discovery_and_session_and_token(self):
        self.reply = lambda m, p, b: (200, {"applications": [{"application_id": "demo"}]})
        self.assertEqual(self.client.list_applications()["applications"][0]["application_id"], "demo")
        self.assertEqual(self.client.session_id, self.session)
        self.assertEqual(self.calls[1][3]["X-Runtime-Session"], self.session)
        self.assertEqual(self.calls[0][3]["Authorization"], "Bearer third-party")
        for call in self.calls:
            headers = {key.lower(): value for key, value in call[3].items()}
            self.assertTrue(headers["x-request-id"].startswith("sdk-"))
        self.assertEqual(len(self.calls), 2)

    def test_connection_auto_revision_and_sync_receipts(self):
        def reply(method, path, body):
            if body["Action"] == "QUERY":
                self.assertEqual(body["connection_deployment_id"], "conn")
                return 200, {"ID": body["ID"], "revision": 7, "Connections": []}
            self.assertEqual(body["expected_revision"], 7)
            self.assertEqual(body["request_id"], body["ID"])
            self.assertNotIn("wait", body)
            return 200, {"ID": body["ID"], "revision": 8, "saved": {"applied": True, "receipts": [{"container": "sink"}]}}
        self.reply = reply
        result = self.client.create_connection("demo", "conn", "Source.CNF", "Sink.REQ", request_id="create-1")
        self.assertEqual(result["revision"], 8)
        self.assertTrue(result["saved"]["applied"])
        self.assertEqual(len(self.calls), 3)

    def test_explicit_revision_event_and_data(self):
        for kind in ("Event", "Data"):
            for method in (self.client.create_connection, self.client.delete_connection):
                self.reply = lambda m, p, b: (200, {"ID": b["ID"], "revision": 5})
                method("demo", "conn", "Source.OUT", "Sink.IN", connection_type=kind, expected_revision=4)
                body = self.calls[-1][2]
                self.assertEqual(body["Connection"]["Type"], kind)
                self.assertEqual(body["expected_revision"], 4)
                self.assertEqual(body["connection_deployment_id"], "conn")
        self.assertEqual(len(self.calls), 5)  # one bootstrap, four mutations

    def test_revision_conflict_no_retry(self):
        self.reply = lambda m, p, b: (409, {"code": "RD721", "message": "stale revision", "details": {"revision": 9, "ID": b["ID"]}})
        error = self.error(lambda: self.client.delete_connection("demo", "conn", "A.CNF", "B.REQ", expected_revision=4, request_id="delete-1"), "RD721", 409)
        self.assertEqual(error.request_id, "delete-1")
        self.assertEqual(error.details["revision"], 9)
        self.assertEqual(len(self.calls), 2)

    def test_parameter_read_and_nested_write_success(self):
        def reply(m, p, b):
            parameter = b["Parameter"]
            if b["Action"] == "READ":
                return 200, {"ID": b["ID"], "Parameter": {"Reference": parameter["Reference"], "Value": 42}}
            return 200, {"ID": b["ID"], "operation": {"state": "succeeded", "operation_id": "op-write", "result": {"Parameter": parameter}}}
        self.reply = reply
        self.assertEqual(self.client.read_parameter("demo", "A.IN")["Parameter"]["Value"], 42)
        result = self.client.write_parameter("demo", "A.IN", [1, 2], request_id="write-1")
        self.assertEqual(result["operation"]["result"]["Parameter"]["Value"], [1, 2])
        self.assertNotIn("Connection", self.calls[-1][2])
        self.assertEqual(self.calls[-1][2]["request_id"], "write-1")

    def test_nested_operation_failure_http_200(self):
        for state in ("failed", "partial"):
            self.reply = lambda m, p, b: (200, {"ID": b["ID"], "operation": {"operation_id": "op-fail", "state": state, "error": {"code": "RD724", "message": "rebuild required", "details": {"agent_code": "AG091"}}}})
            error = self.error(lambda: self.client.write_parameter("demo", "A.IN", 1, request_id="write-fail"), "RD724", 200)
            self.assertEqual(error.request_id, "write-fail")
            self.assertEqual(error.details["agent_code"], "AG091")
            self.assertEqual(error.response["result"]["operation"]["operation_id"], "op-fail")

    def test_operation_running_not_success(self):
        self.reply = lambda m, p, b: (200, {"ID": b["ID"], "operation": {"state": "running", "operation_id": "op-pending"}})
        error = self.error(lambda: self.client.write_parameter("demo", "A.IN", 1), "SDK_OPERATION_INCOMPLETE", 200)
        self.assertEqual(error.details["operation_id"], "op-pending")

    def test_event_bytes_admission_not_completion(self):
        self.reply = lambda m, p, b: (200, {"ID": b["ID"], "accepted": True, "admission": {"ID": b["ID"], "sequence": 4}})
        result = self.client.trigger_event("demo", "A.REQ", payload=b"\x00\xff", request_id="event-1")
        body = self.calls[-1][2]
        self.assertEqual(body["Connection"], {"Source": "$e", "Destination": "A.REQ", "payload_base64": base64.b64encode(b"\x00\xff").decode()})
        self.assertNotIn("request_id", body)
        self.assertTrue(result["accepted"])
        self.assertNotIn("completed", result)

    def test_event_omitted_payload_and_refusal(self):
        self.reply = lambda m, p, b: (200, {"ID": b["ID"], "accepted": False, "Reason": "INVALID_STATE", "refusal_reason": "root_fenced"})
        error = self.error(lambda: self.client.trigger_event("demo", "A.REQ", request_id="refused"), "SDK_EVENT_REJECTED", 200)
        self.assertEqual(error.details["refusal_reason"], "root_fenced")
        self.assertNotIn("payload_base64", self.calls[-1][2]["Connection"])
        self.assertEqual(len(self.calls), 2)

    def test_timeout_no_replay_and_original_request_query(self):
        self.client.capabilities()
        self.client.timeout = 0.02
        def reply(m, p, b):
            if m == "POST":
                time.sleep(0.1)
                return 200, {"ID": b["ID"], "revision": 2}
            return 200, {"request_id": "timeout-1", "complete": True, "result": {"revision": 2}, "error": None}
        self.reply = reply
        error = self.error(lambda: self.client.create_connection("demo", "conn", "A.CNF", "B.REQ", expected_revision=1, request_id="timeout-1"), "SDK_TIMEOUT", None)
        self.assertTrue(error.outcome_unknown)
        self.assertEqual(error.request_id, "timeout-1")
        self.client.timeout = 1
        self.assertTrue(self.client.get_request_result(error.request_id)["complete"])
        self.assertEqual(sum(call[0] == "POST" for call in self.calls), 1)

    def test_event_and_parameter_timeout_no_retry(self):
        self.client.capabilities()
        self.client.timeout = 0.02
        def reply(m, p, b):
            time.sleep(0.1)
            return 200, {"ID": b["ID"]}
        self.reply = reply
        for call in (lambda: self.client.trigger_event("demo", "A.REQ", request_id="event-timeout"),
                     lambda: self.client.write_parameter("demo", "A.IN", 1, request_id="write-timeout")):
            error = self.error(call, "SDK_TIMEOUT", None)
            self.assertTrue(error.outcome_unknown)
        self.assertEqual(len(self.calls), 3)

    def test_old_session_rejected_no_refresh_or_replay(self):
        self.client.capabilities()
        self.session = "session-two"
        self.reply = lambda m, p, b: (409, {"code": "RD017", "message": "ended session", "details": {"runtime_session_id": self.session}})
        self.error(lambda: self.client.trigger_event("demo", "A.REQ", request_id="old-event"), "RD017", 409)
        self.assertEqual(self.client.session_id, "session-one")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1][3]["X-Runtime-Session"], "session-one")

    def test_capabilities_changed_without_fence(self):
        self.client.capabilities()
        self.session = "session-two"
        self.error(self.client.capabilities, "RD017", 200)
        self.assertEqual(self.client.session_id, "session-one")

    def test_queries_do_not_choose_objects_and_encode_selectors(self):
        self.client.query_function_blocks("demo", container="control")
        self.assertEqual(self.calls[-1][2]["DST"], "control")
        self.client.query_parameters("demo", container="control")
        self.assertEqual(self.calls[-1][2]["Parameter"]["Reference"], "*")
        self.client.query_connections("demo", "explicit-conn")
        self.assertEqual(self.calls[-1][2]["connection_deployment_id"], "explicit-conn")
        self.client.get_execution_state("demo", since="a&b=?")
        self.assertTrue(self.calls[-1][1].endswith("?since=a%26b%3D%3F"))
        with self.assertRaises(ValueError):
            self.client.query_parameters("demo")
        with self.assertRaises(TypeError):
            self.client.query_connections("demo")

    def test_invalid_json_and_identity_mismatch(self):
        self.reply = lambda m, p, b: (200, b"not json")
        error = self.error(lambda: self.client.trigger_event("demo", "A.REQ"), "SDK_PROTOCOL", 200)
        self.assertTrue(error.outcome_unknown)
        self.reply = lambda m, p, b: (200, {"ID": "wrong", "accepted": True})
        error = self.error(lambda: self.client.trigger_event("demo", "A.REQ"), "SDK_PROTOCOL", 200)
        self.assertTrue(error.outcome_unknown)

    def test_failed_connection_result_is_inspectable(self):
        self.reply = lambda m, p, b: (200, {"request_id": "failed-1", "complete": True, "result": None, "error": {"code": "RD721"}})
        self.assertEqual(self.client.get_request_result("failed-1")["error"]["code"], "RD721")

    def test_client_validation_before_commands(self):
        for timeout in (0, -1, float("nan"), True):
            with self.assertRaises(ValueError):
                ManagementClient(timeout=timeout)
        with self.assertRaises(ValueError):
            ManagementClient("file:///etc/passwd")
        with self.assertRaises(ValueError):
            self.client.get_application("../other")
        with self.assertRaises(TypeError):
            self.client.trigger_event("demo", "A.REQ", payload="text")
        with self.assertRaises(ValueError):
            self.client.delete_connection("demo", "conn", "A.CNF", "B.REQ", expected_revision=True)
        with self.assertRaises(ValueError):
            self.client.write_parameter("demo", "A.IN", float("nan"))
        self.assertFalse(any(call[0] == "POST" for call in self.calls))


if __name__ == "__main__":
    unittest.main()
