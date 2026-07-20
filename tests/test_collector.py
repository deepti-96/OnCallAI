import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CollectorTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.logs_root = Path(self.temp_dir.name) / "logs"
        for folder in ("db", "infra", "web"):
            (self.logs_root / folder).mkdir(parents=True, exist_ok=True)

        (self.logs_root / "db" / "generic.log").write_text(
            "database pool health is nominal\n",
            encoding="utf-8",
        )
        (self.logs_root / "db" / "matched.log").write_text(
            "connection refused ECONNREFUSED while talking to payment-service\n",
            encoding="utf-8",
        )
        (self.logs_root / "web" / "app.log").write_text(
            "HTTP 500 from checkout-service\n",
            encoding="utf-8",
        )

        from app.agents import collector_agent
        from app.middleware import log_collection
        from app.db import dal

        self.dal = importlib.reload(dal)
        self.collector = importlib.reload(collector_agent)
        self.log_collection = importlib.reload(log_collection)
        self.dal.DB_FILE = self.db_path
        self.dal.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_log_collection_profile_uses_service_context(self):
        incident = {
            "service": "payment-service",
            "environment": "prod",
            "severity": "CRITICAL",
            "payload": {
                "source": "database-cpu",
                "details": "connection refused from service",
            },
        }

        profile = self.log_collection.build_log_collection_profile(incident)

        self.assertEqual(profile["folder"], "db")
        self.assertEqual(profile["time_window_minutes"], 60)
        self.assertIn("payment-service", profile["search_terms"])
        self.assertEqual(profile["catalog"]["owner_team"], "payments-platform")

    def test_collector_ranks_matching_logs_first(self):
        incident_id = self.dal.record_incident(
            status="OPEN",
            service="payment-service",
            environment="prod",
            severity="CRITICAL",
            payload={
                "source": "database-cpu",
                "details": "connection refused from service",
            },
        )
        incident = {
            "id": "incident-1",
            "service": "payment-service",
            "environment": "prod",
            "severity": "CRITICAL",
            "payload": {
                "source": "database-cpu",
                "details": "connection refused from service",
            },
        }

        with patch.object(self.collector, "LOGS_LOCAL_ROOT", str(self.logs_root)):
            collection = self.collector.collector_run({**incident, "id": incident_id})

        self.assertEqual(collection["folder"], "db")
        self.assertGreaterEqual(len(collection["selected_files"]), 2)
        self.assertTrue(collection["selected_files"][0].endswith("matched.log"))
        self.assertIn("ECONNREFUSED", collection["logs"][0])
        self.assertIn("Selected db logs", collection["profile"]["reason"])


if __name__ == "__main__":
    unittest.main()
