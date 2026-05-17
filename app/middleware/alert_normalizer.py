import datetime
import hashlib
from typing import Any, Dict, Iterable


SEVERITY_KEYWORDS = (
    ("critical", "CRITICAL"),
    ("high", "HIGH"),
    ("medium", "MEDIUM"),
    ("low", "LOW"),
)


def _first_non_empty(values: Iterable[Any], default: str = "unknown") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _normalize_timestamp(timestamp: Any) -> str:
    if not timestamp:
        return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    text = str(timestamp).strip()
    if text.endswith("+0000"):
        text = text[:-5] + "Z"
    return text


def infer_service(alert: Dict[str, Any]) -> str:
    trigger = alert.get("Trigger") or {}
    dimensions = trigger.get("Dimensions") or []
    dimension_map = {
        str(item.get("name", "")).lower(): item.get("value")
        for item in dimensions
        if isinstance(item, dict)
    }

    alarm_name = str(alert.get("AlarmName", "")).strip()
    custom_service = (alert.get("OnCallAI") or {}).get("service")

    if custom_service:
        return str(custom_service)

    if dimension_map.get("servicename"):
        return str(dimension_map["servicename"])
    if dimension_map.get("service"):
        return str(dimension_map["service"])
    if dimension_map.get("functionname"):
        return str(dimension_map["functionname"])

    if alarm_name:
        prefix = alarm_name.split("-", 1)[0].strip()
        if prefix:
            return prefix

    return "unknown-service"


def infer_environment(alert: Dict[str, Any]) -> str:
    trigger = alert.get("Trigger") or {}
    dimensions = trigger.get("Dimensions") or []
    dimension_map = {
        str(item.get("name", "")).lower(): item.get("value")
        for item in dimensions
        if isinstance(item, dict)
    }
    custom_env = (alert.get("OnCallAI") or {}).get("environment")
    return _first_non_empty(
        (
            custom_env,
            dimension_map.get("environment"),
            dimension_map.get("env"),
            alert.get("Region"),
        ),
        default="prod",
    )


def infer_severity(alert: Dict[str, Any]) -> str:
    custom_severity = str((alert.get("OnCallAI") or {}).get("severity", "")).strip()
    if custom_severity:
        return custom_severity.upper()

    text = " ".join(
        str(value)
        for value in (
            alert.get("AlarmName", ""),
            alert.get("NewStateReason", ""),
        )
    ).lower()

    for keyword, severity in SEVERITY_KEYWORDS:
        if keyword in text:
            return severity

    return "HIGH" if str(alert.get("NewStateValue", "")).upper() == "ALARM" else "MEDIUM"


def normalize_cloudwatch_alarm(alert: Dict[str, Any]) -> Dict[str, Any]:
    dedupe_source = "|".join(
        [
            infer_service(alert),
            infer_environment(alert),
            str(alert.get("AlarmArn") or alert.get("AlarmName") or ""),
        ]
    )
    dedupe_key = hashlib.sha256(dedupe_source.encode("utf-8")).hexdigest()[:16]
    payload = {
        "source": "cloudwatch",
        "alert_type": "cloudwatch_alarm",
        "alarm_name": alert.get("AlarmName"),
        "alarm_arn": alert.get("AlarmArn"),
        "state": alert.get("NewStateValue"),
        "reason": alert.get("NewStateReason"),
        "region": alert.get("Region"),
        "trigger": alert.get("Trigger"),
        "dedupe_key": dedupe_key,
        "occurrence_count": 1,
        "first_seen_at": _normalize_timestamp(alert.get("StateChangeTime")),
        "last_seen_at": _normalize_timestamp(alert.get("StateChangeTime")),
        "raw_alert": alert,
    }

    return {
        "status": "OPEN" if str(alert.get("NewStateValue", "")).upper() == "ALARM" else "DONE",
        "service": infer_service(alert),
        "environment": infer_environment(alert),
        "severity": infer_severity(alert),
        "payload": payload,
        "created_at": _normalize_timestamp(alert.get("StateChangeTime")),
    }
