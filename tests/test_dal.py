import importlib
import tempfile
import unittest
from pathlib import Path


class DalTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")

        from app.db import dal

        self.dal = importlib.reload(dal)
        self.dal.DB_FILE = self.db_path
        self.dal.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_incident_decodes_payload_json(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="checkout-service",
            environment="prod",
            severity="HIGH",
            payload={"source": "database", "alert_type": "db connectivity"},
        )

        incident = self.dal.get_incident(incident_id)

        self.assertEqual(incident["payload"]["source"], "database")
        self.assertEqual(incident["payload"]["alert_type"], "db connectivity")

    def test_list_incidents_sorts_by_created_at_desc(self):
        older_id = self.dal.record_incident(
            status="OPEN",
            service="service-a",
            environment="prod",
            severity="LOW",
            payload={},
            created_at="2026-01-01T00:00:00Z",
        )
        newer_id = self.dal.record_incident(
            status="OPEN",
            service="service-b",
            environment="prod",
            severity="CRITICAL",
            payload={},
            created_at="2026-02-01T00:00:00Z",
        )

        incidents = self.dal.list_incidents(limit=10)

        self.assertEqual(incidents[0]["id"], newer_id)
        self.assertEqual(incidents[1]["id"], older_id)

    def test_list_incidents_exposes_summary_fields_from_payload(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "cloudwatch",
                "state": "ALARM",
                "alarm_name": "payment-service-critical-latency",
                "occurrence_count": 3,
                "last_seen_at": "2026-02-01T00:05:00Z",
                "enrichment": {
                    "owner_team": "payments-platform",
                    "primary_contact": "payments-oncall",
                    "escalation_policy": "page-payments-primary",
                },
            },
            created_at="2026-02-01T00:00:00Z",
        )

        incidents = self.dal.list_incidents(limit=10)
        incident = next(item for item in incidents if item["id"] == incident_id)

        self.assertEqual(incident["source"], "cloudwatch")
        self.assertEqual(incident["alert_state"], "ALARM")
        self.assertEqual(incident["occurrence_count"], 3)
        self.assertEqual(incident["last_seen_at"], "2026-02-01T00:05:00Z")
        self.assertEqual(incident["owner_team"], "payments-platform")
        self.assertIsInstance(incident["age_minutes"], int)
        self.assertEqual(incident["escalation_priority"], "Immediate")
        self.assertEqual(incident["escalation_target"], "payments-oncall")
        self.assertTrue(incident["should_page"])
        self.assertIn("3 repeated alerts", incident["escalation_reason"])


if __name__ == "__main__":
    unittest.main()
