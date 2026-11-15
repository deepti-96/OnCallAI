"""CloudWatch alarm -> SNS topic -> SQS queue -> OnCallAI.

Why this shape: CloudWatch alarms can only notify SNS. SNS can push to SQS.
OnCallAI long-polls SQS, so it works from a laptop with no public URL, and
a message is only deleted after the incident and its logs are stored. If
OnCallAI is down, alarms wait in the queue.

Per message:
  1. unwrap the SNS envelope (or a raw-delivery body) into the alarm JSON
  2. read routing hints from the alarm description:
       {"oncallai": {"service": "...", "environment": "...", "log_groups": ["..."]}}
  3. on ALARM: FilterLogEvents on those log groups for the minutes before the alarm
  4. write the lines where the collector reads, then ingest via the existing path
  5. delete the message
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List

from app.db import dal
from app.integrations.common import remember_lines, write_incident_logs
from app.middleware.alert_ingest import ingest_cloudwatch_alert

LOOKBACK_MINUTES = int(os.getenv("CW_LOG_LOOKBACK_MINUTES", "15"))
MAX_LOG_EVENTS = int(os.getenv("CW_MAX_LOG_EVENTS", "200"))
LOG_GROUP_PATTERN = os.getenv("CW_LOG_GROUP_PATTERN", "")  # e.g. /oncallai-demo/{service}


def parse_message_body(body: str) -> Dict[str, Any]:
    doc = json.loads(body)
    if isinstance(doc, dict) and doc.get("Type") == "Notification" and isinstance(doc.get("Message"), str):
        doc = json.loads(doc["Message"])  # standard SNS -> SQS envelope
    if not isinstance(doc, dict) or "AlarmName" not in doc:
        raise ValueError("SQS message is not a CloudWatch alarm notification")
    return doc


def apply_routing_hints(alert: Dict[str, Any]) -> List[str]:
    """Copy hints from AlarmDescription into the OnCallAI block the normalizer already reads."""
    hints: Dict[str, Any] = {}
    try:
        hints = (json.loads(alert.get("AlarmDescription") or "{}") or {}).get("oncallai") or {}
    except (json.JSONDecodeError, AttributeError):
        hints = {}
    block = dict(alert.get("OnCallAI") or {})
    for key in ("service", "environment", "severity"):
        if hints.get(key):
            block[key] = hints[key]
    if block:
        alert["OnCallAI"] = block
    groups = [g for g in hints.get("log_groups", []) if isinstance(g, str)]
    if not groups and LOG_GROUP_PATTERN and block.get("service"):
        groups = [LOG_GROUP_PATTERN.format(service=block["service"])]
    return groups


def _alarm_time_ms(alert: Dict[str, Any]) -> int:
    raw = str(alert.get("StateChangeTime") or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return int(datetime.datetime.strptime(raw.replace("Z", "+0000"), fmt).timestamp() * 1000)
        except ValueError:
            continue
    return int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)


def fetch_logs(logs_client: Any, log_groups: List[str], end_ms: int) -> List[Dict[str, Any]]:
    start_ms = end_ms - LOOKBACK_MINUTES * 60_000
    lines: List[Dict[str, Any]] = []
    for group in log_groups:
        kwargs = {"logGroupName": group, "startTime": start_ms, "endTime": end_ms + 60_000, "limit": MAX_LOG_EVENTS}
        while True:
            resp = logs_client.filter_log_events(**kwargs)
            for ev in resp.get("events", []):
                ts = datetime.datetime.fromtimestamp(ev["timestamp"] / 1000, datetime.UTC)
                lines.append({"ts": ev["timestamp"], "time": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "origin": group, "message": str(ev.get("message", "")).rstrip()})
            token = resp.get("nextToken")
            if not token or len(lines) >= MAX_LOG_EVENTS * len(log_groups):
                break
            kwargs["nextToken"] = token
    lines.sort(key=lambda l: l["ts"])
    return lines[-MAX_LOG_EVENTS:]


class CloudWatchSqsSource:
    def __init__(self, sqs_client: Any, logs_client: Any, queue_url: str, logs_root: str, label: str = "cloudwatch"):
        self.sqs = sqs_client
        self.logs = logs_client
        self.queue_url = queue_url
        self.logs_root = logs_root
        self.label = label
        self.stats = {"messages": 0, "incidents": 0, "log_lines": 0, "errors": 0, "last_error": None}

    def handle(self, body: str) -> str:
        alert = parse_message_body(body)
        groups = apply_routing_hints(alert)
        lines: List[Dict[str, Any]] = []
        if str(alert.get("NewStateValue", "")).upper() == "ALARM" and groups:
            lines = fetch_logs(self.logs, groups, _alarm_time_ms(alert))
            path = write_incident_logs(self.logs_root, alert, lines, prefix="cw")
        else:
            path = None
        incident_id = ingest_cloudwatch_alert(alert)
        dal.record_step(incident_id, "ingest", "logs",
                        f"Pulled {len(lines)} CloudWatch log lines from {len(groups)} log group(s)",
                        {"log_groups": groups, "file": str(path) if path else None, "via": self.label}, status="OK")
        remember_lines(self.label, (alert.get("OnCallAI") or {}).get("service", ""), lines)
        self.stats["log_lines"] += len(lines)
        return incident_id

    def poll_once(self, wait_seconds: int = 10) -> List[str]:
        resp = self.sqs.receive_message(QueueUrl=self.queue_url, MaxNumberOfMessages=10,
                                        WaitTimeSeconds=wait_seconds)
        ids: List[str] = []
        for msg in resp.get("Messages", []):
            self.stats["messages"] += 1
            try:
                ids.append(self.handle(msg["Body"]))
                self.stats["incidents"] += 1
            except Exception as exc:  # leave it in the queue; SQS redelivers after the visibility timeout
                self.stats["errors"] += 1
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
                continue
            self.sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=msg["ReceiptHandle"])
        return ids


def from_env(logs_root: str) -> CloudWatchSqsSource | None:
    queue_url = os.getenv("CW_SQS_QUEUE_URL")
    if not queue_url:
        return None
    import boto3  # imported lazily so local runs need no AWS SDK
    region = os.getenv("AWS_REGION", "us-east-1")
    return CloudWatchSqsSource(boto3.client("sqs", region_name=region),
                               boto3.client("logs", region_name=region), queue_url, logs_root)
