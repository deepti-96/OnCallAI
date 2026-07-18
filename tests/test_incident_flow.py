import importlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.errors import RetryableIncidentError, TerminalIncidentError


class OnCallAITestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.logs_root = Path(self.temp_dir.name) / "logs"
        for folder in ("db", "infra", "web"):
            log_dir = self.logs_root / folder
            log_dir.mkdir(parents=True, exist_ok=True)

        (self.logs_root / "db" / "incident.log").write_text(
            "database connection refused ECONNREFUSED\n",
            encoding="utf-8",
        )
        (self.logs_root / "infra" / "incident.log").write_text(
            "OOMKilled on node\n",
            encoding="utf-8",
        )
        (self.logs_root / "web" / "incident.log").write_text(
            "HTTP 500 NullPointerException\n",
            encoding="utf-8",
        )

        from app.db import dal
        from app.agents import collector_agent, analyst_agent, supervisor
        import app.runner as runner

        self.dal = importlib.reload(dal)
        self.collector = importlib.reload(collector_agent)
        self.analyst = importlib.reload(analyst_agent)
        self.supervisor = importlib.reload(supervisor)
        self.runner = importlib.reload(runner)

        self.dal.DB_FILE = self.db_path
        self.dal.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_collector_routes_db_alerts_using_payload(self):
        incident = {
            "id": "incident-1",
            "service": "payment-service",
            "payload": {
                "source": "database-cpu",
                "alert_type": "db availability",
            },
        }
        self.dal.record_incident(
            status="OPEN",
            service=incident["service"],
            environment="prod",
            severity="CRITICAL",
            payload=incident["payload"],
            incident_id=incident["id"],
        )

        with patch.object(self.collector, "LOGS_LOCAL_ROOT", str(self.logs_root)):
            result = self.collector.collector_run(incident)

        self.assertEqual(result["folder"], "db")
        self.assertTrue(result["logs"])
        self.assertIn("ECONNREFUSED", result["logs"][0])

    def test_analyst_uses_retrieved_examples_to_enrich_analysis(self):
        incident = {
            "id": "incident-2",
            "service": "payment-service",
            "environment": "prod",
            "severity": "CRITICAL",
            "payload": {"source": "database", "details": "ECONNREFUSED spikes"},
        }
        self.dal.record_incident(
            status="OPEN",
            service=incident["service"],
            environment=incident["environment"],
            severity=incident["severity"],
            payload=incident["payload"],
            incident_id=incident["id"],
        )

        analysis = self.analyst.analyze_logs(
            incident,
            {"logs": ["database connection refused ECONNREFUSED from app"]},
        )

        self.assertEqual(analysis["issue"], "Database connection errors")
        self.assertGreaterEqual(analysis["confidence"], 0.75)
        self.assertTrue(analysis["retrieved_examples"])
        self.assertTrue(any("Retrieved example" in item for item in analysis["evidence"]))

    def test_process_incident_records_steps_and_final_report(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "database-cpu",
                "details": "ECONNREFUSED from service",
                "enrichment": {
                    "owner_team": "payments-platform",
                    "primary_contact": "payments-oncall",
                    "runbook_url": "https://internal.example/runbooks/payment-service",
                    "escalation_policy": "page-payments-primary",
                    "service_tier": "tier-1",
                }
            },
        )
        incident = self.dal.get_incident(incident_id)

        with patch.object(self.collector, "LOGS_LOCAL_ROOT", str(self.logs_root)):
            self.runner.process_incident(incident)

        processed_incident = self.dal.get_incident(incident_id)
        steps = self.dal.list_steps(incident_id)
        report = self.dal.get_latest_report(incident_id)

        self.assertEqual(processed_incident["status"], "OPEN")
        self.assertEqual(processed_incident["workflow_status"], "COMPLETED")
        self.assertGreaterEqual(len(steps), 5)
        self.assertIsNotNone(report)
        self.assertEqual(report["report"]["issue"], "Database connection errors")
        self.assertIn("Retrieved Context", report["report_md"])
        self.assertIn("Service Context", report["report_md"])
        self.assertIn("Escalation Guidance", report["report_md"])
        self.assertEqual(report["report"]["escalation"]["priority"], "Immediate")
        self.assertEqual(report["report"]["escalation"]["target"], "payments-oncall")

    def test_process_incident_skips_recovered_alerts(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="inventory-service",
            environment="prod",
            severity="HIGH",
            payload={
                "source": "cloudwatch",
                "state": "OK",
                "alert_type": "cloudwatch_alarm",
            },
        )
        incident = self.dal.get_incident(incident_id)

        self.runner.process_incident(incident)

        processed_incident = self.dal.get_incident(incident_id)
        steps = self.dal.list_steps(incident_id)
        report = self.dal.get_latest_report(incident_id)

        self.assertEqual(processed_incident["status"], "RESOLVED")
        self.assertEqual(processed_incident["workflow_status"], "COMPLETED")
        self.assertEqual(processed_incident["resolution_status"], "RESOLVED")
        self.assertEqual(steps[-1]["phase"], "skip")
        self.assertIsNone(report)

    def test_queue_claimed_incident_runs_end_to_end(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "database-cpu",
                "dedupe_key": "payment-service-queue-test",
                "details": "ECONNREFUSED from service",
                "enrichment": {
                    "owner_team": "payments-platform",
                    "primary_contact": "payments-oncall",
                    "runbook_url": "https://internal.example/runbooks/payment-service",
                    "escalation_policy": "page-payments-primary",
                    "service_tier": "tier-1",
                }
            },
        )
        self.dal.enqueue_incident(incident_id)
        incident = self.dal.claim_next_queued_incident()

        self.assertIsNotNone(incident)
        self.assertEqual(incident["id"], incident_id)

        with patch.object(self.collector, "LOGS_LOCAL_ROOT", str(self.logs_root)):
            self.runner.process_incident(incident)

        processed_incident = self.dal.get_incident(incident_id)
        steps = self.dal.list_steps(incident_id)
        report = self.dal.get_latest_report(incident_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            queue_row = conn.execute(
                "SELECT status, attempts FROM incident_queue WHERE incident_id=?",
                (incident_id,),
            ).fetchone()

        self.assertEqual(processed_incident["status"], "OPEN")
        self.assertEqual(processed_incident["workflow_status"], "COMPLETED")
        self.assertGreaterEqual(len(steps), 5)
        self.assertIsNotNone(report)
        self.assertEqual(queue_row[0], "DONE")
        self.assertEqual(queue_row[1], 1)
        self.assertIsNotNone(processed_incident["event_time"])
        self.assertIsNotNone(processed_incident["ingested_at"])
        self.assertIsNotNone(processed_incident["processed_at"])
        self.assertIsNotNone(processed_incident["completed_at"])
        self.assertIsNotNone(incident["queue_claimed_at"])

    def test_retryable_processing_error_requeues_incident(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "database-cpu",
                "dedupe_key": "payment-service-retry-test",
                "details": "ECONNREFUSED from service",
                "enrichment": {
                    "owner_team": "payments-platform",
                    "primary_contact": "payments-oncall",
                    "runbook_url": "https://internal.example/runbooks/payment-service",
                    "escalation_policy": "page-payments-primary",
                    "service_tier": "tier-1",
                }
            },
        )
        self.dal.enqueue_incident(incident_id)
        incident = self.dal.claim_next_queued_incident()

        with (
            patch.object(self.runner, "collector_run", side_effect=RetryableIncidentError("temporary logs unavailable")),
            patch("builtins.print") as mock_print,
        ):
            self.runner.process_incident(incident)

        processed_incident = self.dal.get_incident(incident_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            queue_row = conn.execute(
                "SELECT status, last_error, dead_letter_at FROM incident_queue WHERE incident_id=?",
                (incident_id,),
            ).fetchone()

        printed_events = [json.loads(call.args[0]) for call in mock_print.call_args_list if call.args]

        self.assertEqual(processed_incident["status"], "OPEN")
        self.assertEqual(queue_row[0], "PENDING")
        self.assertIn("RetryableIncidentError", queue_row[1])
        self.assertIsNone(queue_row[2])
        self.assertTrue(any(event["event"] == "incident_requeued" for event in printed_events))

    def test_terminal_processing_error_dead_letters_incident(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "database-cpu",
                "dedupe_key": "payment-service-terminal-test",
                "details": "corrupt payload",
                "enrichment": {
                    "owner_team": "payments-platform",
                    "primary_contact": "payments-oncall",
                    "runbook_url": "https://internal.example/runbooks/payment-service",
                    "escalation_policy": "page-payments-primary",
                    "service_tier": "tier-1",
                }
            },
        )
        self.dal.enqueue_incident(incident_id)
        incident = self.dal.claim_next_queued_incident()

        with (
            patch.object(self.runner, "collector_run", side_effect=TerminalIncidentError("invalid incident payload")),
            patch("builtins.print") as mock_print,
        ):
            self.runner.process_incident(incident)

        processed_incident = self.dal.get_incident(incident_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            queue_row = conn.execute(
                "SELECT status, last_error, dead_letter_at FROM incident_queue WHERE incident_id=?",
                (incident_id,),
            ).fetchone()

        printed_events = [json.loads(call.args[0]) for call in mock_print.call_args_list if call.args]

        self.assertEqual(processed_incident["status"], "FAILED")
        self.assertEqual(queue_row[0], "DEAD_LETTER")
        self.assertIn("TerminalIncidentError", queue_row[1])
        self.assertIsNotNone(queue_row[2])
        self.assertTrue(any(event["event"] == "incident_dead_lettered" for event in printed_events))


if __name__ == "__main__":
    unittest.main()
