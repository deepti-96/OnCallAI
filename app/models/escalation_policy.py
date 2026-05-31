import datetime
from typing import Any, Dict


def _parse_iso(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
    except ValueError:
        return None


def _age_minutes(incident: Dict[str, Any]) -> int:
    payload = incident.get("payload") or {}
    reference_ts = _parse_iso(payload.get("last_seen_at")) or _parse_iso(incident.get("created_at"))
    if reference_ts is None:
        return 0
    delta = datetime.datetime.now(datetime.UTC) - reference_ts
    return max(int(delta.total_seconds() // 60), 0)


def compute_escalation_guidance(incident: Dict[str, Any]) -> Dict[str, Any]:
    payload = incident.get("payload") or {}
    enrichment = payload.get("enrichment") or {}

    severity = str(incident.get("severity", "LOW")).upper()
    occurrence_count = int(payload.get("occurrence_count", 1) or 1)
    age_minutes = _age_minutes(incident)
    service_tier = enrichment.get("service_tier", "")
    primary_contact = enrichment.get("primary_contact", "service-oncall")
    escalation_policy = enrichment.get("escalation_policy", "page-service-primary")

    priority = "Monitor"
    if severity == "CRITICAL" or occurrence_count >= 5:
        priority = "Immediate"
    elif severity == "HIGH" or age_minutes >= 60 or service_tier == "tier-1":
        priority = "High"
    elif severity == "MEDIUM" or age_minutes >= 30:
        priority = "Elevated"

    reasons = []
    if severity == "CRITICAL":
        reasons.append("critical severity")
    elif severity == "HIGH":
        reasons.append("high severity")
    if occurrence_count >= 3:
        reasons.append(f"{occurrence_count} repeated alerts")
    if age_minutes >= 60:
        reasons.append(f"open for {age_minutes} minutes")
    if service_tier == "tier-1":
        reasons.append("tier-1 service")
    if not reasons:
        reasons.append("continue monitoring")

    should_page = priority in {"Immediate", "High"}
    target = primary_contact if should_page else enrichment.get("owner_team", primary_contact)
    action = (
        f"Page {target} via {escalation_policy}"
        if should_page
        else f"Notify {target} and continue investigation"
    )

    return {
        "priority": priority,
        "should_page": should_page,
        "target": target,
        "policy": escalation_policy,
        "reason": ", ".join(reasons),
        "age_minutes": age_minutes,
        "occurrence_count": occurrence_count,
        "action": action,
    }
