import pathlib
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import AWS_REGION, CLOUDWATCH_MAX_RECORDS, POLL_INTERVAL_SECONDS
from app.middleware.alert_ingest import ingest_cloudwatch_alert

try:
    import boto3
except ImportError:  # Optional in local-only development
    boto3 = None


def build_cloudwatch_alarm_event(alarm: Dict[str, Any], region: str) -> Dict[str, Any]:
    state = alarm.get("StateValue", "ALARM")
    reason = alarm.get("StateReason", "")
    updated_at = alarm.get("StateUpdatedTimestamp")
    if hasattr(updated_at, "strftime"):
        updated_at = updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "AlarmName": alarm.get("AlarmName"),
        "AlarmArn": alarm.get("AlarmArn"),
        "NewStateValue": state,
        "NewStateReason": reason,
        "StateChangeTime": updated_at,
        "Region": region,
        "Trigger": {
            "MetricName": alarm.get("MetricName"),
            "Namespace": alarm.get("Namespace"),
            "Dimensions": alarm.get("Dimensions", []),
        },
    }


def list_alarm_events(
    client: Any,
    *,
    state_value: str = "ALARM",
    max_records: int = CLOUDWATCH_MAX_RECORDS,
    region: str = AWS_REGION,
) -> List[Dict[str, Any]]:
    paginator = getattr(client, "get_paginator", None)
    alarms: List[Dict[str, Any]] = []

    if callable(paginator):
        for page in client.get_paginator("describe_alarms").paginate(
            StateValue=state_value,
            PaginationConfig={"MaxItems": max_records},
        ):
            alarms.extend(page.get("MetricAlarms", []))
            if len(alarms) >= max_records:
                break
    else:
        response = client.describe_alarms(StateValue=state_value, MaxRecords=max_records)
        alarms.extend(response.get("MetricAlarms", []))

    return [build_cloudwatch_alarm_event(alarm, region) for alarm in alarms[:max_records]]


def list_alarm_events_for_states(
    client: Any,
    *,
    state_values: Sequence[str],
    max_records: int = CLOUDWATCH_MAX_RECORDS,
    region: str = AWS_REGION,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for state_value in state_values:
        for event in list_alarm_events(
            client,
            state_value=state_value,
            max_records=max_records,
            region=region,
        ):
            key = (event.get("AlarmArn") or "", event.get("NewStateValue") or "")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            events.append(event)
            if len(events) >= max_records:
                return events

    return events


def poll_cloudwatch_once(
    *,
    client: Any | None = None,
    state_values: Sequence[str] = ("ALARM", "OK"),
    max_records: int = CLOUDWATCH_MAX_RECORDS,
    region: str = AWS_REGION,
) -> List[str]:
    if client is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required for real CloudWatch polling")
        client = boto3.client("cloudwatch", region_name=region)

    incident_ids: List[str] = []
    for event in list_alarm_events_for_states(
        client,
        state_values=state_values,
        max_records=max_records,
        region=region,
    ):
        incident_ids.append(ingest_cloudwatch_alert(event))
    return incident_ids


def run_polling_loop(
    *,
    interval_seconds: int = POLL_INTERVAL_SECONDS,
    client: Any | None = None,
    region: str = AWS_REGION,
    iterations: Optional[int] = None,
) -> List[List[str]]:
    results: List[List[str]] = []
    count = 0

    while iterations is None or count < iterations:
        incident_ids = poll_cloudwatch_once(client=client, region=region)
        results.append(incident_ids)
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(interval_seconds)

    return results


if __name__ == "__main__":
    incident_ids = poll_cloudwatch_once()
    print(f"Ingested {len(incident_ids)} CloudWatch alarm(s): {incident_ids}")
