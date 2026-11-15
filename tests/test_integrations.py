import importlib
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch


class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from app.db import dal
        from app.agents import collector_agent
        self.dal = importlib.reload(dal)
        self.dal.DB_FILE = str(Path(self.tmp.name) / "t.db")
        self.dal.init_db()
        self.logs_root = str(Path(self.tmp.name) / "logs")
        self.collector = collector_agent
        from app.integrations import cloudwatch_sqs, datadog, replay
        self.cw, self.dd, self.replay = cloudwatch_sqs, datadog, replay

    def tearDown(self):
        self.tmp.cleanup()


class CloudWatchSqsTests(IntegrationTestCase):
    def test_sns_envelope_and_raw_delivery_both_parse(self):
        body, _ = self.replay.scenario("pool-exhaustion")
        alarm = self.cw.parse_message_body(body)
        self.assertEqual(alarm["AlarmName"], "checkout-service-error-burst")
        self.assertEqual(self.cw.parse_message_body(json.dumps(alarm))["NewStateValue"], "ALARM")
        with self.assertRaises(ValueError):
            self.cw.parse_message_body(json.dumps({"hello": "world"}))

    def test_routing_hints_feed_the_existing_normalizer(self):
        alarm = self.cw.parse_message_body(self.replay.scenario("pool-exhaustion")[0])
        groups = self.cw.apply_routing_hints(alarm)
        self.assertEqual(alarm["OnCallAI"], {"service": "checkout-service", "environment": "prod"})
        self.assertIn("/oncallai-demo/payment-service", groups)

    def test_alarm_creates_incident_pulls_logs_and_deletes_message(self):
        body, logs = self.replay.scenario("pool-exhaustion")
        sqs, cwlogs = self.replay.FakeSqs([body]), self.replay.FakeLogs(logs)
        src = self.cw.CloudWatchSqsSource(sqs, cwlogs, "q", self.logs_root)
        ids = src.poll_once(wait_seconds=0)
        self.assertEqual(len(ids), 1)
        self.assertEqual(sqs.queue, [])
        inc = self.dal.get_incident(ids[0])
        self.assertEqual((inc["service"], inc["environment"]), ("checkout-service", "prod"))
        self.assertEqual(len(cwlogs.calls), 2)
        files = list(Path(self.logs_root).rglob("cw-*.log"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text()
        self.assertIn("HTTP 504", text)
        self.assertIn("payment-service v2.15.0", text)
        # the existing collector, unchanged, finds that file for this incident
        with patch.object(self.collector, "LOGS_LOCAL_ROOT", self.logs_root):
            collected = self.collector.collector_run(inc)
        self.assertIn(str(files[0]), collected["selected_files"])

    def test_bad_message_stays_in_queue(self):
        sqs = self.replay.FakeSqs(["not json"])
        src = self.cw.CloudWatchSqsSource(sqs, self.replay.FakeLogs({}), "q", self.logs_root)
        self.assertEqual(src.poll_once(wait_seconds=0), [])
        self.assertEqual(len(sqs.queue), 1)
        self.assertEqual(src.stats["errors"], 1)

    def test_recovery_alarm_resolves_the_open_incident(self):
        first = self.replay.replay("pool-exhaustion", self.logs_root)[0]
        second = self.replay.replay("recovery", self.logs_root)[0]
        self.assertEqual(first, second)
        self.assertEqual(self.dal.get_incident(first)["resolution_status"], "RESOLVED")

    def test_log_window_is_bounded_to_before_the_alarm(self):
        body, logs = self.replay.scenario("pool-exhaustion")
        old = {"timestamp": 1_000, "message": "ERROR ancient line"}
        logs["/oncallai-demo/checkout-service"].append(old)
        cwlogs = self.replay.FakeLogs(logs)
        self.cw.CloudWatchSqsSource(self.replay.FakeSqs([body]), cwlogs, "q", self.logs_root).poll_once(0)
        text = next(Path(self.logs_root).rglob("cw-*.log")).read_text()
        self.assertNotIn("ancient line", text)


class DatadogTests(IntegrationTestCase):
    PAYLOAD = {"alert_id": "123", "title": "[Triggered] checkout 5xx rate high", "transition": "Triggered",
               "priority": "P1", "message": "5xx rate above 5% on POST /api/cart/submit", "date": "1763170000000",
               "tags": "service:checkout-service,env:prod,team:checkout", "query": "sum:trace.http.errors{*}",
               "link": "https://app.datadoghq.com/monitors/123"}

    def test_payload_maps_to_alarm_shape(self):
        alarm = self.dd.to_alarm(self.PAYLOAD)
        self.assertEqual(alarm["NewStateValue"], "ALARM")
        self.assertEqual(alarm["OnCallAI"], {"service": "checkout-service", "environment": "prod", "severity": "CRITICAL"})
        self.assertEqual(self.dd.to_alarm(dict(self.PAYLOAD, transition="Recovered"))["NewStateValue"], "OK")

    def test_webhook_without_keys_opens_incident_without_logs(self):
        with patch.dict(os.environ, {"DD_API_KEY": "", "DD_APP_KEY": ""}):
            out = self.dd.handle_webhook(self.PAYLOAD, self.logs_root)
        inc = self.dal.get_incident(out["incident_id"])
        self.assertEqual(inc["payload"]["source"], "datadog")
        self.assertEqual(inc["severity"], "CRITICAL")
        self.assertEqual(out["log_lines"], 0)

    def test_webhook_pulls_logs_from_logs_search_api(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, self.headers["DD-API-KEY"], self.headers["DD-APPLICATION-KEY"],
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                out = json.dumps({"data": [{"attributes": {"timestamp": "2026-11-15T01:00:00.000Z", "service": "checkout-service",
                                                           "status": "error", "message": "HTTP 504 on POST /api/cart/submit"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with patch.dict(os.environ, {"DD_API_KEY": "k", "DD_APP_KEY": "a",
                                         "DD_API_BASE": f"http://127.0.0.1:{srv.server_port}"}):
                out = self.dd.handle_webhook(self.PAYLOAD, self.logs_root)
        finally:
            srv.shutdown()
        self.assertEqual(out["log_lines"], 1)
        path, api, app, body = seen[0]
        self.assertEqual((path, api, app), ("/api/v2/logs/events/search", "k", "a"))
        self.assertEqual(body["filter"]["query"], "service:checkout-service")
        self.assertIn("HTTP 504", next(Path(self.logs_root).rglob("dd-*.log")).read_text())


class ConsoleEndToEndTest(IntegrationTestCase):
    def test_replay_triage_resolve_writeback_over_http(self):
        from app.web import server
        importlib.reload(server)
        with patch.dict(os.environ, {"MIND_ENABLED": "false", "CW_SQS_QUEUE_URL": ""}):
            server.build_app(self.dal.DB_FILE, self.logs_root, simulate_mind=True)
        stop = threading.Event()
        threading.Thread(target=server.worker_loop, args=(stop,), daemon=True).start()
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_port}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())

        try:
            self.assertIn("On-call triage that remembers", urllib.request.urlopen(base + "/").read().decode())
            self.assertIn("Alert sources", urllib.request.urlopen(base + "/console").read().decode())
            self.assertEqual(urllib.request.urlopen(base + "/static/theme.css").status, 200)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/static/../server.py")
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/static/%2e%2e/server.py")
            seeded = call("/api/demo/history", {})["seeded"]
            self.assertTrue(all(s["status"] == "written" for s in seeded))
            inc_id = call("/api/demo/replay", {"scenario": "pool-exhaustion"})["incidents"][0]
            for _ in range(50):
                detail = call(f"/api/incidents/{inc_id}")
                if detail["report"]:
                    break
                time.sleep(0.1)
            hist = detail["report"]["report"]["historical_context"]
            self.assertEqual(hist["status"], "ok")
            self.assertGreaterEqual(hist["historical_incidents"], 1)
            r = call(f"/api/incidents/{inc_id}/resolve", {"root_cause": "payment-service v2.15.0 shrank its DB pool",
                                                         "mitigation": ["Restore pool size"]})
            self.assertEqual(r["status"], "written")
            state = call("/api/state")
            self.assertEqual(state["mind"]["mode"], "simulated")
            self.assertTrue(state["logs"])
        finally:
            stop.set()
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
