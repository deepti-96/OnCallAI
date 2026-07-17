import importlib
import sqlite3
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

        self.assertIsInstance(incident_id, str)
        self.assertEqual(incident["payload"]["source"], "database")
        self.assertEqual(incident["payload"]["alert_type"], "db connectivity")
        self.assertEqual(incident["event_time"], incident["created_at"])
        self.assertIsNotNone(incident["ingested_at"])

    def test_get_incident_exposes_enriched_triage_fields(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "cloudwatch",
                "state": "ALARM",
                "occurrence_count": 4,
                "last_seen_at": "2026-02-01T00:05:00Z",
                "enrichment": {
                    "owner_team": "payments-platform",
                    "primary_contact": "payments-oncall",
                    "escalation_policy": "page-payments-primary",
                },
            },
            created_at="2026-02-01T00:00:00Z",
        )

        incident = self.dal.get_incident(incident_id)

        self.assertEqual(incident["occurrence_count"], 4)
        self.assertEqual(incident["last_seen_at"], "2026-02-01T00:05:00Z")
        self.assertEqual(incident["escalation_priority"], "Immediate")
        self.assertEqual(incident["escalation_target"], "payments-oncall")
        self.assertTrue(incident["should_page"])

    def test_markers_set_processing_timestamps(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={"source": "cloudwatch"},
        )

        self.dal.mark_in_progress(incident_id)
        in_progress = self.dal.get_incident(incident_id)
        self.dal.mark_done(incident_id)
        completed = self.dal.get_incident(incident_id)

        self.assertEqual(in_progress["status"], "IN_PROGRESS")
        self.assertIsNotNone(in_progress["processed_at"])
        self.assertEqual(completed["status"], "DONE")
        self.assertIsNotNone(completed["completed_at"])

    def test_find_open_incident_by_dedupe_key_uses_direct_lookup(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "cloudwatch",
                "dedupe_key": "payment-service-prod-alarm",
            },
        )

        incident = self.dal.find_open_incident_by_dedupe_key("payment-service-prod-alarm")

        self.assertIsNotNone(incident)
        self.assertEqual(incident["id"], incident_id)
        self.assertEqual(incident["payload"]["dedupe_key"], "payment-service-prod-alarm")

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

    def test_agent_steps_and_reports_cascade_when_incident_is_deleted(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={"source": "cloudwatch"},
        )
        self.dal.record_step(
            incident_id,
            "collector",
            "start",
            "Collector started",
        )
        self.dal.save_report(
            incident_id,
            {"issue": "example"},
            "# Example",
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM incidents WHERE id=?", (incident_id,))

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            step_count = conn.execute(
                "SELECT COUNT(*) FROM agent_steps WHERE incident_id=?",
                (incident_id,),
            ).fetchone()[0]
            report_count = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE incident_id=?",
                (incident_id,),
            ).fetchone()[0]

        self.assertEqual(step_count, 0)
        self.assertEqual(report_count, 0)

    def test_queue_helpers_claim_and_complete_incidents(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={"source": "cloudwatch", "dedupe_key": "queue-test"},
        )

        self.dal.enqueue_incident(incident_id)
        claimed = self.dal.claim_next_queued_incident()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], incident_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            queue_row = conn.execute(
                "SELECT status, attempts FROM incident_queue WHERE incident_id=?",
                (incident_id,),
            ).fetchone()

        self.assertEqual(queue_row[0], "IN_PROGRESS")
        self.assertEqual(queue_row[1], 1)

        self.dal.complete_queued_incident(incident_id, status="DONE")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            queue_row = conn.execute(
                "SELECT status FROM incident_queue WHERE incident_id=?",
                (incident_id,),
            ).fetchone()

        self.assertEqual(queue_row[0], "DONE")


if __name__ == "__main__":
    unittest.main()
