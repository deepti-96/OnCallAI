import json
from pathlib import Path
from typing import Any, Dict

from app.db.dal import get_open_incidents, init_db, record_incident, record_step, update_incident
from app.middleware.alert_normalizer import normalize_cloudwatch_alarm
from app.models.service_registry import get_service_enrichment


def _find_deduped_incident(normalized: Dict[str, Any]) -> Dict[str, Any] | None:
    dedupe_key = (normalized.get("payload") or {}).get("dedupe_key")
    if not dedupe_key:
        return None

    for incident in get_open_incidents():
        payload = incident.get("payload") or {}
        if payload.get("dedupe_key") == dedupe_key:
            return incident
    return None


def _merge_payload(existing_payload: Dict[str, Any], new_payload: Dict[str, Any], created_at: str) -> Dict[str, Any]:
    merged = dict(existing_payload)
    merged.update(new_payload)
    merged["occurrence_count"] = int(existing_payload.get("occurrence_count", 1)) + 1
    merged["first_seen_at"] = existing_payload.get("first_seen_at") or new_payload.get("first_seen_at") or created_at
    merged["last_seen_at"] = created_at
    merged["raw_alert"] = new_payload.get("raw_alert", existing_payload.get("raw_alert"))
    history = list(existing_payload.get("alert_history", []))
    history.append(
        {
            "state": new_payload.get("state"),
            "reason": new_payload.get("reason"),
            "seen_at": created_at,
        }
    )
    merged["alert_history"] = history[-10:]
    return merged


def _apply_enrichment(normalized: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(normalized.get("payload") or {})
    enrichment = get_service_enrichment(
        normalized["service"],
        normalized.get("environment"),
    )
    if enrichment:
        payload["enrichment"] = enrichment
    normalized["payload"] = payload
    return normalized


def ingest_cloudwatch_alert(alert: Dict[str, Any]) -> str:
    normalized = _apply_enrichment(normalize_cloudwatch_alarm(alert))
    init_db()
    existing = _find_deduped_incident(normalized)
    if existing:
        merged_payload = _merge_payload(
            existing.get("payload") or {},
            normalized.get("payload") or {},
            normalized["created_at"],
        )
        update_incident(
            existing["id"],
            status=normalized["status"],
            severity=normalized["severity"],
            payload=merged_payload,
            created_at=normalized["created_at"],
        )
        phase = "resolve" if normalized["status"] == "DONE" else "dedupe"
        message = (
            "Resolved existing incident from recovery alert"
            if normalized["status"] == "DONE"
            else "Merged repeated alert into existing incident"
        )
        record_step(
            existing["id"],
            "ingest",
            phase,
            message,
            {
                "source": merged_payload.get("source"),
                "alarm_name": merged_payload.get("alarm_name"),
                "state": merged_payload.get("state"),
                "occurrence_count": merged_payload.get("occurrence_count"),
            },
            status="OK",
        )
        return existing["id"]
    incident_id = record_incident(**normalized)
    payload = normalized.get("payload") or {}
    record_step(
        incident_id,
        "ingest",
        "create",
        "Created incident from incoming alert",
        {
            "source": payload.get("source"),
            "alarm_name": payload.get("alarm_name"),
            "state": payload.get("state"),
            "occurrence_count": payload.get("occurrence_count", 1),
        },
        status="OK",
    )
    return incident_id


def ingest_cloudwatch_alert_file(path: str) -> str:
    alert = json.loads(Path(path).read_text(encoding="utf-8"))
    return ingest_cloudwatch_alert(alert)
