import unittest

from app.middleware.alert_normalizer import (
    infer_environment,
    infer_service,
    infer_severity,
    normalize_cloudwatch_alarm,
)


class AlertNormalizerTestCase(unittest.TestCase):
    def setUp(self):
        self.alert = {
            "AlarmName": "payment-service-critical-latency",
            "NewStateValue": "ALARM",
            "NewStateReason": "Critical latency threshold breached",
            "StateChangeTime": "2026-04-12T10:00:00Z",
            "Region": "us-east-1",
            "Trigger": {
                "Dimensions": [
                    {"name": "service", "value": "payment-service"},
                    {"name": "environment", "value": "prod"},
                ]
            },
        }

    def test_infer_service_from_dimensions(self):
        self.assertEqual(infer_service(self.alert), "payment-service")

    def test_infer_environment_from_dimensions(self):
        self.assertEqual(infer_environment(self.alert), "prod")

    def test_infer_severity_from_alarm_metadata(self):
        self.assertEqual(infer_severity(self.alert), "CRITICAL")

    def test_normalize_cloudwatch_alarm(self):
        normalized = normalize_cloudwatch_alarm(self.alert)

        self.assertEqual(normalized["status"], "OPEN")
        self.assertEqual(normalized["service"], "payment-service")
        self.assertEqual(normalized["environment"], "prod")
        self.assertEqual(normalized["severity"], "CRITICAL")
        self.assertEqual(normalized["created_at"], "2026-04-12T10:00:00Z")
        self.assertEqual(normalized["payload"]["source"], "cloudwatch")
        self.assertEqual(normalized["payload"]["alert_type"], "cloudwatch_alarm")


if __name__ == "__main__":
    unittest.main()
