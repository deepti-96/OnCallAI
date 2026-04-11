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


if __name__ == "__main__":
    unittest.main()
