import importlib
import unittest


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        return iter(self.pages)


class FakeCloudWatchClient:
    def __init__(self, alarms):
        self.alarms = alarms
        self.calls = []

    def get_paginator(self, name):
        if name != "describe_alarms":
            raise ValueError(name)
        client = self

        class RecordingPaginator:
            def paginate(self, **kwargs):
                client.calls.append(kwargs)
                state_value = kwargs.get("StateValue")
                filtered = [alarm for alarm in client.alarms if alarm.get("StateValue") == state_value]
                return iter([{"MetricAlarms": filtered}])

        return RecordingPaginator()


class CloudWatchBotoTestCase(unittest.TestCase):
    def setUp(self):
        from app.middleware import cloudwatch_boto

        self.cloudwatch_boto = importlib.reload(cloudwatch_boto)
        self.alarms = [
            {
                "AlarmName": "payment-service-critical-latency",
                "AlarmArn": "arn:aws:cloudwatch:us-east-1:123:alarm:payment-service-critical-latency",
                "StateValue": "ALARM",
                "StateReason": "Latency threshold breached",
                "StateUpdatedTimestamp": "2026-05-02T10:00:00Z",
                "MetricName": "Duration",
                "Namespace": "AWS/Lambda",
                "Dimensions": [
                    {"name": "service", "value": "payment-service"},
                    {"name": "environment", "value": "prod"},
                ],
            },
            {
                "AlarmName": "inventory-service-high-errors",
                "AlarmArn": "arn:aws:cloudwatch:us-east-1:123:alarm:inventory-service-high-errors",
                "StateValue": "OK",
                "StateReason": "Error rate recovered",
                "StateUpdatedTimestamp": "2026-05-02T10:05:00Z",
                "MetricName": "Errors",
                "Namespace": "AWS/Lambda",
                "Dimensions": [
                    {"name": "service", "value": "inventory-service"},
                    {"name": "environment", "value": "prod"},
                ],
            },
        ]

    def test_build_cloudwatch_alarm_event_maps_alarm_shape(self):
        event = self.cloudwatch_boto.build_cloudwatch_alarm_event(self.alarms[0], "us-east-1")

        self.assertEqual(event["AlarmName"], self.alarms[0]["AlarmName"])
        self.assertEqual(event["NewStateValue"], "ALARM")
        self.assertEqual(event["Region"], "us-east-1")
        self.assertEqual(event["Trigger"]["MetricName"], "Duration")

    def test_list_alarm_events_uses_client_results(self):
        client = FakeCloudWatchClient(self.alarms)

        events = self.cloudwatch_boto.list_alarm_events(client, region="us-east-1")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["AlarmName"], self.alarms[0]["AlarmName"])

    def test_list_alarm_events_for_states_includes_recovery_events(self):
        client = FakeCloudWatchClient(self.alarms)

        events = self.cloudwatch_boto.list_alarm_events_for_states(
            client,
            state_values=("ALARM", "OK"),
            region="us-east-1",
        )

        self.assertEqual(
            [event["NewStateValue"] for event in events],
            ["ALARM", "OK"],
        )
        self.assertEqual(
            [call["StateValue"] for call in client.calls],
            ["ALARM", "OK"],
        )

    def test_poll_cloudwatch_once_ingests_each_alarm(self):
        client = FakeCloudWatchClient(self.alarms)
        ingested = []

        def fake_ingest(alert):
            ingested.append(alert["AlarmName"])
            return f"incident-{len(ingested)}"

        self.cloudwatch_boto.ingest_cloudwatch_alert = fake_ingest

        incident_ids = self.cloudwatch_boto.poll_cloudwatch_once(client=client, region="us-east-1")

        self.assertEqual(
            ingested,
            [self.alarms[0]["AlarmName"], self.alarms[1]["AlarmName"]],
        )
        self.assertEqual(incident_ids, ["incident-1", "incident-2"])

    def test_run_polling_loop_respects_iteration_limit(self):
        client = FakeCloudWatchClient(self.alarms)
        self.cloudwatch_boto.ingest_cloudwatch_alert = lambda alert: "incident-1"

        results = self.cloudwatch_boto.run_polling_loop(
            client=client,
            region="us-east-1",
            interval_seconds=0,
            iterations=2,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], ["incident-1", "incident-1"])


if __name__ == "__main__":
    unittest.main()
