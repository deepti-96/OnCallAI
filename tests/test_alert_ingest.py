import importlib
import json
import tempfile
import unittest
from pathlib import Path


class AlertIngestTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.alert_path = Path(self.temp_dir.name) / "alert.json"

        from app.db import dal
        from app.middleware import alert_ingest, cloudwatch_simulator

        self.dal = importlib.reload(dal)
        self.alert_ingest = importlib.reload(alert_ingest)
        self.cloudwatch_simulator = importlib.reload(cloudwatch_simulator)

        self.dal.DB_FILE = self.db_path
        self.alert_ingest.init_db = self.dal.init_db
        self.alert_ingest.record_incident = self.dal.record_incident
        self.alert_ingest.record_step = self.dal.record_step
        self.alert_ingest.get_open_incidents = self.dal.get_open_incidents
        self.alert_ingest.update_incident = self.dal.update_incident
        self.dal.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ingest_cloudwatch_alert_creates_incident(self):
        alert = self.cloudwatch_simulator.sample_cloudwatch_alarm(
            service="checkout-service",
            environment="staging",
            severity="HIGH",
        )

        incident_id = self.alert_ingest.ingest_cloudwatch_alert(alert)
        incident = self.dal.get_incident(incident_id)

        self.assertEqual(incident["service"], "checkout-service")
        self.assertEqual(incident["environment"], "staging")
        self.assertEqual(incident["severity"], "HIGH")
        self.assertEqual(incident["status"], "OPEN")
        self.assertEqual(incident["payload"]["source"], "cloudwatch")
        self.assertEqual(
            incident["payload"]["enrichment"]["owner_team"],
            "checkout-experience",
        )
        steps = self.dal.list_steps(incident_id)
        self.assertEqual(steps[0]["agent"], "ingest")
        self.assertEqual(steps[0]["phase"], "create")

    def test_ingest_cloudwatch_alert_file_reads_json_payload(self):
        alert = self.cloudwatch_simulator.sample_cloudwatch_alarm(service="orders-service")
        self.alert_path.write_text(json.dumps(alert), encoding="utf-8")

        incident_id = self.alert_ingest.ingest_cloudwatch_alert_file(str(self.alert_path))
        incident = self.dal.get_incident(incident_id)

        self.assertEqual(incident["service"], "orders-service")
        self.assertEqual(incident["payload"]["alarm_name"], alert["AlarmName"])

    def test_repeated_alert_reuses_existing_open_incident(self):
        alert = self.cloudwatch_simulator.sample_cloudwatch_alarm(service="payments-service")

        first_id = self.alert_ingest.ingest_cloudwatch_alert(alert)
        second_id = self.alert_ingest.ingest_cloudwatch_alert(alert)

        incident = self.dal.get_incident(first_id)
        incidents = self.dal.list_incidents(limit=10)

        self.assertEqual(first_id, second_id)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incident["payload"]["occurrence_count"], 2)
        self.assertEqual(len(incident["payload"]["alert_history"]), 1)
        steps = self.dal.list_steps(first_id)
        self.assertEqual(steps[-1]["phase"], "dedupe")

    def test_ok_alert_resolves_existing_open_incident(self):
        open_alert = self.cloudwatch_simulator.sample_cloudwatch_alarm(
            service="inventory-service",
            state="ALARM",
        )
        resolved_alert = self.cloudwatch_simulator.sample_cloudwatch_alarm(
            service="inventory-service",
            state="OK",
        )

        incident_id = self.alert_ingest.ingest_cloudwatch_alert(open_alert)
        resolved_id = self.alert_ingest.ingest_cloudwatch_alert(resolved_alert)

        incident = self.dal.get_incident(incident_id)
        incidents = self.dal.list_incidents(limit=10)

        self.assertEqual(incident_id, resolved_id)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incident["status"], "DONE")
        self.assertEqual(incident["payload"]["state"], "OK")
        self.assertEqual(incident["payload"]["occurrence_count"], 2)
        steps = self.dal.list_steps(incident_id)
        self.assertEqual(steps[-1]["phase"], "resolve")


if __name__ == "__main__":
    unittest.main()
