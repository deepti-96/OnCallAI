import copy
import importlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch


class MindMemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        from app.db import dal
        from app.memory import incident_memory, telemetry
        from app.agents import analyst_agent, collector_agent, supervisor
        import app.runner as runner

        self.dal = importlib.reload(dal)
        self.dal.DB_FILE = str(Path(self.temp_dir.name) / "test.db")
        self.dal.init_db()
        self.mem = importlib.reload(incident_memory)
        self.analyst = importlib.reload(analyst_agent)
        self.collector = importlib.reload(collector_agent)
        self.supervisor = importlib.reload(supervisor)
        self.runner = importlib.reload(runner)
        self.telemetry = telemetry
        self.telemetry.reset()

        from app.memory import demo_data
        from app.memory.fake_mind import FakeMind, StrictFakeMind
        from app.memory.mind_client import MindUnavailable
        self.data = demo_data
        self.FakeMind, self.StrictFakeMind, self.MindUnavailable = FakeMind, StrictFakeMind, MindUnavailable

    def tearDown(self):
        self.temp_dir.cleanup()

    # helpers -------------------------------------------------------------
    def _record(self, scenario):
        inc = copy.deepcopy(scenario)
        self.dal.record_incident(status="OPEN", service=inc["service"], environment=inc["environment"],
                                 severity=inc["severity"], payload=inc["payload"], incident_id=inc["id"])
        return self.dal.get_incident(inc["id"]), {"logs": inc["logs"]}

    def _seed(self, fake, *scenarios):
        for sc in scenarios:
            inc, collected = self._record(sc)
            res = self.mem.remember_resolution(inc, sc["resolution"], collected, client=fake)
            self.assertEqual(res["status"], "written")

    def _analyze_b(self, fake):
        inc, collected = self._record(self.data.INCIDENT_B)
        with patch.object(self.mem, "get_client", return_value=fake):
            return self.analyst.analyze_logs(inc, collected)

    # 1. successful historical retrieval ------------------------------------
    def test_successful_historical_retrieval(self):
        fake = self.FakeMind()
        self._seed(fake, self.data.INCIDENT_C)
        analysis = self._analyze_b(fake)
        hist = analysis["historical_context"]
        self.assertEqual(hist["status"], "ok")
        self.assertEqual(hist["historical_incidents"], 1)
        self.assertTrue(hist["used_in_rca"])
        self.assertEqual(hist["hypotheses"][0]["memory_key"], self.mem.memory_key("demo-inc-C"))
        self.assertTrue(analysis["provenance"]["historical_mind"])
        self.assertEqual(self.telemetry.COUNTERS["mind_query_succeeded"], 1)

    def test_graph_hop_finds_root_incident_and_skips_lookalike(self):
        fake = self.FakeMind()
        self._seed(fake, self.data.INCIDENT_A, self.data.INCIDENT_C, self.data.INCIDENT_D)
        hist = self._analyze_b(fake)["historical_context"]
        keys = [h["memory_key"] for h in hist["hypotheses"]]
        self.assertIn(self.mem.memory_key("demo-inc-C"), keys)
        self.assertIn(self.mem.memory_key("demo-inc-A"), keys)
        self.assertNotIn(self.mem.memory_key("demo-inc-D"), keys)
        a = next(h for h in hist["hypotheses"] if h["memory_key"] == self.mem.memory_key("demo-inc-A"))
        self.assertTrue(any("reached through" in r for r in a["match_reasons"]))

    def test_history_is_not_copied_as_the_root_cause(self):
        fake = self.FakeMind()
        self._seed(fake, self.data.INCIDENT_A, self.data.INCIDENT_C)
        analysis = self._analyze_b(fake)
        self.assertNotEqual(analysis["root_cause"], self.data.INCIDENT_A["resolution"]["root_cause"])
        a = next(h for h in analysis["historical_context"]["hypotheses"]
                 if h["memory_key"] == self.mem.memory_key("demo-inc-A"))
        self.assertIn("config_change", a["seen_only_in_past"])
        self.assertTrue(all(m.startswith("Check:") for m in analysis["mitigations"]
                            if "worked for" in m))
        _, md = self.supervisor.compile_report(self.dal.get_incident("demo-inc-B"), analysis)
        self.assertIn("Historical Context (MIND, not current evidence)", md)
        self.assertIn("past-only=['config_change']", md)

    # 2. no relevant history -------------------------------------------------
    def test_no_relevant_history(self):
        fake = self.FakeMind()
        self._seed(fake, self.data.INCIDENT_D)
        analysis = self._analyze_b(fake)
        hist = analysis["historical_context"]
        self.assertEqual(hist["status"], "no_history")
        self.assertEqual(hist["historical_incidents"], 0)
        self.assertFalse(hist["used_in_rca"])

    # 3. MIND unavailable ----------------------------------------------------
    def test_mind_unavailable_falls_back(self):
        fake = self.FakeMind(fail_with=self.MindUnavailable("connection reset"))
        analysis = self._analyze_b(fake)
        hist = analysis["historical_context"]
        self.assertEqual(hist["status"], "unavailable")
        self.assertTrue(hist["fallback_activated"])
        self.assertIn("root_cause", analysis)
        self.assertEqual(self.telemetry.COUNTERS["mind_fallback_activated"], 1)

    # 4. malformed / partial response ---------------------------------------
    def test_malformed_response(self):
        analysis = self._analyze_b(self.StrictFakeMind(malformed=True))
        self.assertEqual(analysis["historical_context"]["status"], "malformed")
        self.assertTrue(analysis["historical_context"]["fallback_activated"])

    def test_partial_response_keeps_valid_records(self):
        fake = self.FakeMind()
        self._seed(fake, self.data.INCIDENT_A, self.data.INCIDENT_C)
        fake.corrupt_records = True
        hist = self._analyze_b(fake)["historical_context"]
        self.assertGreaterEqual(hist["partial_records"], 1)
        self.assertIn(hist["status"], {"partial", "no_history", "ok"})

    # 5. duplicate write-back -------------------------------------------------
    def test_duplicate_writeback_is_skipped(self):
        fake = self.FakeMind()
        inc, collected = self._record(self.data.INCIDENT_A)
        first = self.mem.remember_resolution(inc, self.data.INCIDENT_A["resolution"], collected, client=fake)
        second = self.mem.remember_resolution(inc, self.data.INCIDENT_A["resolution"], collected, client=fake)
        self.assertEqual(first["status"], "written")
        self.assertEqual(second["status"], "duplicate_skipped")
        self.assertEqual(len(fake.entries), 1)

    def test_duplicate_detected_in_mind_when_local_ledger_is_lost(self):
        fake = self.FakeMind()
        inc, collected = self._record(self.data.INCIDENT_A)
        self.mem.remember_resolution(inc, self.data.INCIDENT_A["resolution"], collected, client=fake)
        with self.mem._ledger() as con:
            con.execute("DELETE FROM mind_memory_writes")
        again = self.mem.remember_resolution(inc, self.data.INCIDENT_A["resolution"], collected, client=fake)
        self.assertEqual(again["status"], "duplicate_skipped")
        self.assertEqual(len(fake.entries), 1)

    def test_failed_writeback_is_queued_and_retried(self):
        fake = self.FakeMind(fail_with=self.MindUnavailable("503"))
        inc, collected = self._record(self.data.INCIDENT_A)
        res = self.mem.remember_resolution(inc, self.data.INCIDENT_A["resolution"], collected, client=fake)
        self.assertEqual(res["status"], "failed_queued")
        fake.fail_with = None
        self.assertEqual(self.mem.retry_pending_writes(client=fake), 1)
        self.assertEqual(len(fake.entries), 1)

    # 6. successful incident-memory creation ----------------------------------
    def test_incident_memory_creation(self):
        fake = self.FakeMind()
        self._record(self.data.INCIDENT_C)
        res = self.mem.resolve_and_remember(
            "demo-inc-C", self.data.INCIDENT_C["resolution"]["root_cause"],
            self.data.INCIDENT_C["resolution"]["mitigation"], affected_component="payment-service",
            logs=self.data.INCIDENT_C["logs"], client=fake)
        self.assertEqual(res["status"], "written")
        entry = next(iter(fake.entries.values()))
        self.assertIn("checkout-service depends on payment-service.", entry["content"])
        self.assertIn(f"OnCallAI-Incident-Key: {res['memory_key']}", entry["content"])
        self.assertNotRegex(entry["title"], r"[/()]")
        self.assertEqual(self.dal.get_incident("demo-inc-C")["resolution_status"], "RESOLVED")

    # 7. fallback to existing OnCallAI path, end to end -----------------------
    def test_full_pipeline_completes_when_mind_is_down(self):
        logs_root = Path(self.temp_dir.name) / "logs"
        for folder in ("db", "infra", "web"):
            (logs_root / folder).mkdir(parents=True)
            (logs_root / folder / "x.log").write_text("database connection refused ECONNREFUSED\n")
        inc, _ = self._record(self.data.INCIDENT_B)
        fake = self.FakeMind(fail_with=self.MindUnavailable("timeout"))
        with patch.object(self.collector, "LOGS_LOCAL_ROOT", str(logs_root)), \
                patch.object(self.mem, "get_client", return_value=fake):
            self.runner.process_incident(inc)
        report = self.dal.get_latest_report(inc["id"])
        self.assertIsNotNone(report)
        self.assertEqual(self.dal.get_incident(inc["id"])["workflow_status"], "COMPLETED")
        self.assertIn("Retrieved Context", report["report_md"])
        self.assertIn("MIND unavailable", report["report_md"])

    def test_unexpected_memory_error_does_not_break_triage(self):
        inc, collected = self._record(self.data.INCIDENT_B)
        with patch.object(self.analyst, "apply_incident_memory", side_effect=RuntimeError("boom")):
            analysis = self.analyst.analyze_logs(inc, collected)
        self.assertIn("root_cause", analysis)
        self.assertTrue(any(s["agent"] == "memory" and s["status"] == "WARN" for s in self.dal.list_steps(inc["id"])))

    def test_disabled_mind_changes_nothing(self):
        inc, collected = self._record(self.data.INCIDENT_B)
        with patch.object(self.mem, "get_client", return_value=None):
            analysis = self.analyst.analyze_logs(inc, collected)
        self.assertNotIn("historical_context", analysis)
        self.assertNotIn("provenance", analysis)


class MindHttpClientTestCase(unittest.TestCase):
    """The real client against a local HTTP server: checks paths, header and body shape."""

    def test_query_and_create_entry_wire_format(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, payload):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                seen.append((self.path, self.headers["X-API-Key"], json.loads(self.rfile.read(length))))
                if self.path == "/developer/v1/query":
                    self._reply({"response": "ctx", "sources": [], "credits_used": 0, "credits_remaining": 9})
                else:
                    self._reply({"entry_id": "e1"})

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            from app.memory.mind_client import MindClient
            client = MindClient("mind_test", f"http://127.0.0.1:{server.server_port}", timeout=2)
            self.assertEqual(client.query("q", mode="local")["response"], "ctx")
            self.assertEqual(client.create_entry(title="t", content="c", tags=["x"])["entry_id"], "e1")
        finally:
            server.shutdown()
        self.assertEqual(seen[0][0], "/developer/v1/query")
        self.assertEqual(seen[0][1], "mind_test")
        self.assertEqual(seen[0][2], {"query": "q", "mode": "local", "retrieve_only": True})
        self.assertEqual(seen[1][0], "/developer/v1/entries")

    def test_edge_block_is_retried_gzipped(self):
        import gzip
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                enc = self.headers.get("Content-Encoding")
                seen.append(enc)
                if enc != "gzip":  # behave like the web edge on SQL-looking text
                    self.send_response(403)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html>blocked</html>")
                    return
                body = json.loads(gzip.decompress(raw))
                out = json.dumps({"response": body["query"], "sources": []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            from app.memory.mind_client import MindClient
            client = MindClient("mind_test", f"http://127.0.0.1:{server.server_port}", timeout=2)
            q = "SELECT * FROM orders WHERE id=1 OR 1=1; | bash"
            self.assertEqual(client.query(q)["response"], q)
        finally:
            server.shutdown()
        self.assertEqual(seen, [None, "gzip"])

    def test_unreachable_server_raises_unavailable(self):
        from app.memory.mind_client import MindClient, MindUnavailable
        client = MindClient("mind_test", "http://127.0.0.1:9", timeout=0.5)
        with self.assertRaises(MindUnavailable):
            client.query("q")


if __name__ == "__main__":
    unittest.main()
