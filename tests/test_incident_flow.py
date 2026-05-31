import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

        self.assertEqual(processed_incident["status"], "DONE")
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

        self.assertEqual(processed_incident["status"], "DONE")
        self.assertEqual(steps[-1]["phase"], "skip")
        self.assertIsNone(report)


if __name__ == "__main__":
    unittest.main()
