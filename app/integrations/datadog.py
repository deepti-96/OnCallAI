"""Datadog monitor -> webhook -> OnCallAI.

In Datadog: Integrations -> Webhooks -> New. URL: https://<your-host>/api/webhooks/datadog
Custom header (optional): {"X-OnCallAI-Token": "<DATADOG_WEBHOOK_TOKEN>"}
Payload (paste as is; Datadog fills the $VARIABLES at send time):

    {"alert_id": "$ALERT_ID", "title": "$EVENT_TITLE", "transition": "$ALERT_TRANSITION",
     "priority": "$ALERT_PRIORITY", "message": "$TEXT_ONLY_MSG", "date": "$DATE",
     "tags": "$TAGS", "query": "$ALERT_QUERY", "link": "$LINK"}

Then mention @webhook-<name> in a monitor's message.

Logs: if DD_API_KEY and DD_APP_KEY are set, the logs around the alert are
pulled from the Logs Search API (POST /api/v2/logs/events/search). The app
key needs the logs_read_data permission.
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.request
from typing import Any, Dict, List

from app.db import dal
from app.integrations.common import remember_lines, write_incident_logs
from app.middleware.alert_ingest import ingest_cloudwatch_alert

PRIORITY_TO_SEVERITY = {"P1": "CRITICAL", "P2": "HIGH", "P3": "MEDIUM", "P4": "LOW", "P5": "LOW"}


def _tags(raw: Any) -> Dict[str, str]:
    items = raw if isinstance(raw, list) else str(raw or "").split(",")
    out: Dict[str, str] = {}
    for item in items:
        k, _, v = str(item).strip().partition(":")
        if k and v:
            out.setdefault(k, v)
    return out


def _iso(epoch_ms: Any) -> str:
    try:
        ts = int(str(epoch_ms)) / (1000 if len(str(epoch_ms)) > 10 else 1)
        return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_alarm(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map the webhook payload onto the alarm shape the existing normalizer reads."""
    tags = _tags(payload.get("tags"))
    transition = str(payload.get("transition") or "").lower()
    oncall: Dict[str, Any] = {}
    if tags.get("service"):
        oncall["service"] = tags["service"]
    if tags.get("env"):
        oncall["environment"] = tags["env"]
    sev = PRIORITY_TO_SEVERITY.get(str(payload.get("priority") or "").upper())
    if sev:
        oncall["severity"] = sev
    return {
        "AlarmName": payload.get("title") or "datadog-monitor",
        "AlarmArn": f"datadog:monitor:{payload.get('alert_id') or payload.get('title')}",
        "NewStateValue": "OK" if transition.startswith("recovered") else "ALARM",
        "NewStateReason": payload.get("message") or "",
        "StateChangeTime": _iso(payload.get("date")),
        "Region": "datadog",
        "Trigger": {"MetricName": payload.get("query") or "", "Namespace": "datadog", "Dimensions": []},
        "OnCallAI": oncall,
    }


def search_logs(service: str, env: str | None, end_iso: str) -> List[Dict[str, Any]]:
    api_key, app_key = os.getenv("DD_API_KEY"), os.getenv("DD_APP_KEY")
    if not (api_key and app_key and service):
        return []
    site = os.getenv("DD_SITE", "datadoghq.com")
    end = datetime.datetime.strptime(end_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
    lookback = int(os.getenv("DD_LOG_LOOKBACK_MINUTES", "15"))
    query = os.getenv("DD_LOG_QUERY", "service:{service}").format(service=service, env=env or "")
    body = {"filter": {"query": query, "from": (end - datetime.timedelta(minutes=lookback)).isoformat(),
                       "to": (end + datetime.timedelta(minutes=1)).isoformat()},
            "page": {"limit": int(os.getenv("DD_MAX_LOG_EVENTS", "200"))}, "sort": "timestamp"}
    base = os.getenv("DD_API_BASE") or f"https://api.{site}"
    req = urllib.request.Request(f"{base}/api/v2/logs/events/search", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "DD-API-KEY": api_key,
                                          "DD-APPLICATION-KEY": app_key})
    with urllib.request.urlopen(req, timeout=10) as res:
        doc = json.loads(res.read().decode())
    lines = []
    for item in doc.get("data", []):
        a = item.get("attributes") or {}
        lines.append({"time": str(a.get("timestamp", ""))[:19] + "Z", "origin": a.get("service") or service,
                      "message": f"{(a.get('status') or '').upper()} {a.get('message', '')}".strip()})
    return lines


def handle_webhook(payload: Dict[str, Any], logs_root: str) -> Dict[str, Any]:
    alert = to_alarm(payload)
    oncall = alert.get("OnCallAI") or {}
    lines: List[Dict[str, Any]] = []
    error = None
    if alert["NewStateValue"] == "ALARM":
        try:
            lines = search_logs(oncall.get("service", ""), oncall.get("environment"), alert["StateChangeTime"])
        except Exception as exc:  # the incident still opens; the collector just has fewer logs
            error = f"{type(exc).__name__}: {exc}"
        write_incident_logs(logs_root, alert, lines, prefix="dd")
    incident_id = ingest_cloudwatch_alert(alert)
    inc = dal.get_incident(incident_id)
    payload_db = dict((inc or {}).get("payload") or {})
    payload_db.update({"source": "datadog", "alert_type": "datadog_monitor", "link": payload.get("link")})
    dal.update_incident(incident_id, payload=payload_db)
    dal.record_step(incident_id, "ingest", "logs", f"Pulled {len(lines)} Datadog log lines",
                    {"error": error, "query_service": oncall.get("service")}, status="WARN" if error else "OK")
    remember_lines("datadog", oncall.get("service", ""), lines)
    return {"incident_id": incident_id, "log_lines": len(lines), "log_error": error}
