"""Offline Apps HTTP contract tests; only a loopback fake server is started."""
import http.client
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from management_sdk import ManagementClient, ManagementError


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.context = "current-one"
        self.csrf = "csrf-one"
        self.reply = lambda p, b: (200, [])
        self.truncate = False
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def handle_request(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.loads(raw) if raw else None
                path = self.path.removeprefix("/api/v1/management/")
                owner.calls.append((path, body, dict(self.headers)))
                if path == "session":
                    status, result = 200, {"csrf_token": owner.csrf, "context": owner.context}
                else: status, result = owner.reply(path, body)
                if isinstance(result, bytes): data = result
                else:
                    envelope = {"schema_version": 1, "ok": status < 400, "request_id": self.headers.get("X-Request-ID")}
                    envelope["result" if status < 400 else "error"] = result
                    data = json.dumps(envelope).encode()
                self.send_response(status); self.send_header("Content-Length", str(len(data))); self.end_headers()
                try: self.wfile.write(data[:-8] if owner.truncate else data)
                except (BrokenPipeError, ConnectionResetError): pass
            do_GET = handle_request
            do_POST = handle_request
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.worker = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.02), daemon=True)
        self.worker.start()
        self.client = ManagementClient(f"http://127.0.0.1:{self.server.server_port}", timeout=1)
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()
    def error(self, call, code):
        with self.assertRaises(ManagementError) as caught:call()
        self.assertEqual(caught.exception.code,code)
        self.assertTrue(caught.exception.request_id)
        return caught.exception
    def test_types_separate_from_instances_and_encode_name(self):
        self.reply=lambda p,b:(200, [{"name":"sdk::Source"}] if p=="types" else {"name":"sdk::Source","interface":{"event_inputs":[]}})
        self.assertEqual(self.client.list_block_types(),[{"name":"sdk::Source"}])
        self.assertEqual(self.client.get_block_type("sdk::Source")["name"],"sdk::Source")
        self.assertEqual(self.calls[-1][0],"types/sdk%3A%3ASource")
        self.assertFalse(any(path=="session" for path,body,headers in self.calls))
    def test_runtime_selector_is_bound_on_discovery_bootstrap_and_commands(self):
        client = ManagementClient(self.client.base_url, runtime_id="device-b")
        self.reply=lambda p,b:(200,[] if p=="runtimes" else {"completed":True})
        self.assertEqual(client.list_runtimes(), [])
        client.write_parameter("app.Source.IN", 42)
        self.assertEqual([row[0] for row in self.calls], ["runtimes", "session", "parameters/write"])
        self.assertTrue(all(row[2]["X-Runtime-Id"] == "device-b" for row in self.calls))
        for invalid in ("bad\r\nheader", "../device", "", 4):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ManagementClient(self.client.base_url, runtime_id=invalid)
    def test_simple_queries_and_scalar_parameter_read(self):
        self.reply=lambda p,b:(200,17 if p=="parameters/read" else {"state":"active"} if p=="status" else [{"name":"app.Source"}])
        self.assertIsInstance(self.client.list_instances(),list)
        self.assertIsInstance(self.client.get_connections(),list)
        self.assertEqual(self.client.get_status()["state"],"active")
        self.assertEqual(self.client.read_parameter("app.Source.IN"),17)
        self.assertEqual(self.calls[-1][1],{"reference":"app.Source.IN"})
    def test_mutations_without_internal_fields_or_kind(self):
        self.reply=lambda p,b:(200,{"completed":True})
        self.client.create_connection("app.Source.CNF","app.Sink.REQ")
        self.client.delete_connection("app.Source.Value","app.Sink.X")
        for p,b,h in self.calls[1:]:
            self.assertEqual(set(b),{"source","destination"})
            self.assertEqual(h["X-Management-Context"],self.context)
            self.assertNotIn("X-Csrf-Token",h)
            self.assertNotIn("Authorization",h)
            self.assertNotIn("Origin",h)
        self.assertEqual(len(self.calls),3)
    def test_write_and_event_remain_separate(self):
        self.reply=lambda p,b:(200,{"accepted":True} if p=="events/trigger" else {"completed":True})
        self.client.write_parameter("app.Source.IN",[1,2])
        self.assertEqual(self.calls[-1][1],{"reference":"app.Source.IN","value":[1,2]})
        self.assertTrue(self.client.trigger_event("app.Source.REQ")["accepted"])
        self.assertEqual(self.calls[-1][1],{"reference":"app.Source.REQ"})
        with self.assertRaises(TypeError):self.client.trigger_event("app.Source.REQ",payload=b"x")
    def test_function_block_lifecycle_uses_typed_instance_routes(self):
        self.reply=lambda p,b:(200,{"completed":True,"function_blocks":[{"Name":"app.FB","State":"STOPPED"}]})
        for action in ("start", "stop", "kill", "reset"):
            self.assertTrue(getattr(self.client, action + "_function_block")("app.FB")["completed"])
            self.assertEqual(self.calls[-1][0], "function-blocks/" + action)
            self.assertEqual(self.calls[-1][1], {"reference":"app.FB"})

    def test_unfinished_function_block_operation_has_unknown_outcome(self):
        self.reply=lambda p,b:(409,{"code":"RD_OPERATION_INCOMPLETE","message":"operation accepted but incomplete"})
        error = self.error(lambda: self.client.stop_function_block("app.FB"), "RD_OPERATION_INCOMPLETE")
        self.assertTrue(error.outcome_unknown)
        self.assertEqual(len(self.calls), 2)

    def test_no_current_application_and_type_query_still_available(self):
        self.context=None
        self.reply=lambda p,b:(200,[]) if p=="types" else (409,{"code":"MG_NO_CURRENT","message":"No running application"})
        self.assertEqual(self.client.list_block_types(),[])
        error=self.error(self.client.list_instances,"MG_NO_CURRENT")
        self.assertEqual(error.http_status,409)
    def test_multiple_candidates_refused(self):
        self.reply=lambda p,b:(409,{"code":"MG_MULTIPLE_CURRENT","details":{"candidates":["a","b"]}})
        self.assertEqual(self.error(self.client.get_status,"MG_MULTIPLE_CURRENT").details["candidates"],["a","b"])
    def test_revision_conflict_not_retried(self):
        self.reply=lambda p,b:(409,{"code":"RD721","message":"stale revision","details":{"Reason":"INVALID_STATE"}})
        error=self.error(lambda:self.client.delete_connection("a.CNF","b.REQ"),"RD721")
        self.assertEqual(error.details["Reason"],"INVALID_STATE")
        self.assertEqual(len(self.calls),2)
    def test_event_refusal_preserves_receipt(self):
        self.reply=lambda p,b:(409,{"code":"MG_EVENT_REJECTED","details":{"receipt":{"accepted":False,"Reason":"OVERFLOW"}}})
        error=self.error(lambda:self.client.trigger_event("a.REQ"),"MG_EVENT_REJECTED")
        self.assertFalse(error.details["receipt"]["accepted"])
    def test_nested_operation_failure_is_server_error(self):
        self.reply=lambda p,b:(409,{"code":"RD724","details":{"operation":{"state":"failed","operation_id":"op-one"}}})
        error=self.error(lambda:self.client.write_parameter("a.IN",2),"RD724")
        self.assertEqual(error.details["operation"]["operation_id"],"op-one")
    def test_session_change_never_refreshes_or_replays(self):
        self.client.list_instances();self.context="current-two"
        self.reply=lambda p,b:(409,{"code":"MG_SESSION_CHANGED","message":"Reconnect explicitly"})
        self.error(lambda:self.client.trigger_event("a.REQ"),"MG_SESSION_CHANGED")
        self.assertEqual(self.calls[-1][2]["X-Management-Context"],"current-one")
        self.assertEqual(sum(p=="session" for p,b,h in self.calls),1)
    def test_csrf_change_never_retries_mutation(self):
        self.client.list_instances();self.csrf="new-csrf"
        self.reply=lambda p,b:(403,{"code":"csrf_rejected"})
        self.error(lambda:self.client.trigger_event("a.REQ"),"csrf_rejected")
        self.assertEqual(len(self.calls),3)
    def test_timeout_all_mutations_no_repeat(self):
        self.client.list_instances();self.client.timeout=.02
        def reply(p,b):time.sleep(.08);return 200,{"completed":True}
        self.reply=reply
        for call in (lambda:self.client.create_connection("a.CNF","b.REQ"),lambda:self.client.delete_connection("a.OUT","b.IN"),
                     lambda:self.client.write_parameter("a.IN",1),lambda:self.client.trigger_event("a.REQ")):
            self.assertTrue(self.error(call,"SDK_TIMEOUT").outcome_unknown)
        self.assertEqual(len(self.calls),6)
    def test_read_timeout_not_unknown_mutation(self):
        self.client.list_instances();self.client.timeout=.02
        def reply(p,b):time.sleep(.08);return 200,1
        self.reply=reply
        self.assertFalse(self.error(lambda:self.client.read_parameter("a.IN"),"SDK_TIMEOUT").outcome_unknown)
    def test_truncated_response_preserves_identity_and_never_replays(self):
        self.client.list_instances()
        self.reply=lambda p,b:(200,{"completed":True})
        self.truncate=True
        for call,mutating in ((lambda:self.client.create_connection("a.CNF","b.REQ"),True),
                              (lambda:self.client.delete_connection("a.OUT","b.IN"),True),
                              (lambda:self.client.write_parameter("a.IN",1),True),
                              (lambda:self.client.trigger_event("a.REQ"),True),
                              (lambda:self.client.read_parameter("a.IN"),False)):
            before=len(self.calls)
            error=self.error(call,"SDK_TRANSPORT")
            self.assertIsInstance(error.__cause__,http.client.IncompleteRead)
            self.assertEqual(error.http_status,200)
            self.assertEqual(error.request_id,self.calls[-1][2]["X-Request-Id"])
            self.assertEqual(error.outcome_unknown,mutating)
            self.assertEqual(len(self.calls),before+1)
        self.truncate=False
        self.assertTrue(self.client.write_parameter("a.IN",2)["completed"])
    def test_http_exception_before_headers_preserves_identity(self):
        self.client.list_instances()
        for exception in (http.client.BadStatusLine("broken"),http.client.RemoteDisconnected("closed")):
            with patch.object(self.client._opener,"open",side_effect=exception) as opened:
                error=self.error(lambda:self.client.trigger_event("a.REQ"),"SDK_TRANSPORT")
            self.assertIs(error.__cause__,exception)
            self.assertEqual(error.request_id,opened.call_args.args[0].get_header("X-request-id"))
            self.assertIsNone(error.http_status)
            self.assertTrue(error.outcome_unknown)
            opened.assert_called_once()
    def test_foreign_runtime_envelope_and_bad_json_rejected(self):
        self.reply=lambda p,b:(200,b'{"api":"runtime-api/1","ok":true,"result":{}}')
        self.error(self.client.list_instances,"SDK_PROTOCOL")
        self.reply=lambda p,b:(200,b"not JSON")
        self.error(lambda:self.client.trigger_event("a.REQ"),"SDK_PROTOCOL")
    def test_argument_validation_before_sending(self):
        for timeout in (0,-1,True,float('nan')):
            with self.assertRaises(ValueError):ManagementClient(timeout=timeout)
        with self.assertRaises(ValueError):ManagementClient('file:///etc/passwd')
        with self.assertRaises(ValueError):self.client.write_parameter("a.IN",float('inf'))
        self.assertEqual(self.calls,[])
    def test_malformed_error_preserves_correlation(self):
        self.reply=lambda p,b:(500,b'{"schema_version":1,"ok":false,"error":"invalid"}')
        error=self.error(lambda:self.client.trigger_event("a.REQ"),"SDK_PROTOCOL")
        self.assertTrue(error.outcome_unknown)

if __name__=='__main__':unittest.main()
