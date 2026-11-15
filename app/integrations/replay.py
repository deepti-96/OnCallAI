"""Offline replay of a real CloudWatch -> SNS -> SQS delivery.

FakeSqs and FakeLogs expose the same boto3 methods CloudWatchSqsSource calls
(receive_message, delete_message, filter_log_events), so a replay runs the
exact production code path. The message body is the SNS envelope shape AWS
delivers to SQS. Services and log lines are synthetic.
"""
from __future__ import annotations

import datetime
import json
import uuid
from typing import Any, Dict, List

GROUPS = {"checkout-service": "/oncallai-demo/checkout-service",
          "payment-service": "/oncallai-demo/payment-service"}


def _alarm(name: str, service: str, state: str, reason: str, when: datetime.datetime) -> Dict[str, Any]:
    return {
        "AlarmName": name,
        "AlarmDescription": json.dumps({"oncallai": {"service": service, "environment": "prod",
                                                     "log_groups": list(GROUPS.values())}}),
        "AWSAccountId": "000000000000",
        "AlarmArn": f"arn:aws:cloudwatch:us-east-1:000000000000:alarm:{name}",
        "NewStateValue": state,
        "NewStateReason": reason,
        "StateChangeTime": when.strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
        "Region": "US East (N. Virginia)",
        "OldStateValue": "OK" if state == "ALARM" else "ALARM",
        "Trigger": {"MetricName": "ErrorCount", "Namespace": "OnCallAIDemo", "StatisticType": "Statistic",
                    "Statistic": "SUM", "Dimensions": [], "Period": 60, "EvaluationPeriods": 1,
                    "ComparisonOperator": "GreaterThanOrEqualToThreshold", "Threshold": 3.0},
    }


def _sns(alarm: Dict[str, Any]) -> str:
    return json.dumps({"Type": "Notification", "MessageId": str(uuid.uuid4()),
                       "TopicArn": "arn:aws:sns:us-east-1:000000000000:oncallai-alarms",
                       "Subject": f'ALARM: "{alarm["AlarmName"]}" in US East (N. Virginia)',
                       "Message": json.dumps(alarm), "Timestamp": alarm["StateChangeTime"]})


def scenario(name: str) -> tuple[str, Dict[str, List[Dict[str, Any]]]]:
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    ms = lambda dt: int(dt.timestamp() * 1000)  # noqa: E731
    t = lambda sec: ms(now - datetime.timedelta(seconds=sec))  # noqa: E731
    logs: Dict[str, List[Dict[str, Any]]] = {g: [] for g in GROUPS.values()}
    co, pay = GROUPS["checkout-service"], GROUPS["payment-service"]
    if name == "pool-exhaustion":
        logs[pay] += [
            {"timestamp": t(240), "message": "INFO payment-service v2.15.0 deployment rolled out, db pool max=10 (was 50)"},
            {"timestamp": t(200), "message": "WARN payment-service v2.15.0 connection pool exhausted (max=10), request queued 2.9s"},
            {"timestamp": t(150), "message": "WARN payment-service v2.15.0 connection pool exhausted (max=10), request queued 3.4s"},
        ]
        logs[co] += [{"timestamp": t(180 - 20 * i),
                      "message": "ERROR checkout-service HTTP 504 Gateway Timeout on POST /api/cart/submit after 3000ms"}
                     for i in range(6)]
        logs[co].append({"timestamp": t(60), "message": "WARN checkout-service worker threads blocked waiting on downstream response"})
        alarm = _alarm("checkout-service-error-burst", "checkout-service", "ALARM",
                       "Threshold Crossed: 1 datapoint [6.0] was greater than or equal to the threshold (3.0).", now)
    elif name == "config-timeout":
        logs[pay] += [{"timestamp": t(200), "message": "INFO deploy payment-service v2.14.0 config changed CARD_GATEWAY_TIMEOUT_MS 3000 -> 300"}]
        logs[pay] += [{"timestamp": t(150 - 20 * i), "message": "ERROR upstream=card-gateway request timed out after 300ms"}
                      for i in range(5)]
        alarm = _alarm("payment-service-error-burst", "payment-service", "ALARM",
                       "Threshold Crossed: 1 datapoint [5.0] was greater than or equal to the threshold (3.0).", now)
    elif name == "recovery":
        alarm = _alarm("checkout-service-error-burst", "checkout-service", "OK",
                       "Threshold Crossed: 1 datapoint [0.0] was not greater than or equal to the threshold (3.0).", now)
    else:
        raise ValueError(f"unknown scenario {name}")
    return _sns(alarm), logs


class FakeSqs:
    def __init__(self, bodies: List[str]):
        self.queue = [{"MessageId": str(uuid.uuid4()), "ReceiptHandle": str(uuid.uuid4()), "Body": b} for b in bodies]
        self.deleted: List[str] = []

    def receive_message(self, QueueUrl, MaxNumberOfMessages=1, WaitTimeSeconds=0, **_):
        return {"Messages": self.queue[:MaxNumberOfMessages]} if self.queue else {}

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)
        self.queue = [m for m in self.queue if m["ReceiptHandle"] != ReceiptHandle]


class FakeLogs:
    def __init__(self, events_by_group: Dict[str, List[Dict[str, Any]]]):
        self.events = events_by_group
        self.calls: List[Dict[str, Any]] = []

    def filter_log_events(self, logGroupName, startTime, endTime, limit=10000, nextToken=None, **_):
        self.calls.append({"logGroupName": logGroupName, "startTime": startTime, "endTime": endTime})
        evs = [e for e in self.events.get(logGroupName, []) if startTime <= e["timestamp"] <= endTime]
        return {"events": [dict(e, logStreamName="replay", eventId=str(i)) for i, e in enumerate(evs[:limit])]}


def replay(name: str, logs_root: str) -> List[str]:
    from app.integrations.cloudwatch_sqs import CloudWatchSqsSource
    body, logs = scenario(name)
    src = CloudWatchSqsSource(FakeSqs([body]), FakeLogs(logs), "replay://oncallai-alarms", logs_root, label="replay")
    return src.poll_once(wait_seconds=0)
