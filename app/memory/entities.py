"""Pull graph-friendly entities out of an incident and its collected logs.

These are the nouns MIND's graph extraction should link: services,
dependencies, deployments, error types. Rule-based on purpose, so the
output is deterministic and testable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.models.service_registry import load_service_catalog, resolve_service_name

ERROR_TYPES = {
    "timeout": r"timed? ?out|timeout|deadline exceeded|HTTP 504",
    "connection_refused": r"connection refused|ECONNREFUSED",
    "pool_exhausted": r"pool exhausted|too many connections|no available connections",
    "oom": r"OOMKilled|OutOfMemoryError",
    "http_5xx": r"HTTP 5\d\d|\b5\d\d\b status|5xx",
    "null_pointer": r"NullPointerException|null deref",
    "config_change": r"config(uration)? (change|changed|updated)|env var .* changed",
}

VERSION_RE = re.compile(r"\b([a-z][a-z0-9-]*)[@ ]v(\d+\.\d+(?:\.\d+)?)\b", re.I)
DEP_RE = re.compile(r"(?:upstream|dependency|calling|call to|downstream)[=: ]+([a-z][a-z0-9-]+)", re.I)


def _known_services() -> set[str]:
    return set(load_service_catalog().keys())


def extract_entities(incident: Dict[str, Any], collected: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = incident.get("payload") or {}
    enrichment = payload.get("enrichment") or {}
    logs: List[str] = list((collected or {}).get("logs", []))
    text = "\n".join(
        str(v) for v in [payload.get("alert", ""), payload.get("details", ""), payload.get("reason", ""), *logs] if v
    )

    service = resolve_service_name(incident.get("service", "")) or incident.get("service", "unknown")

    deps: List[str] = []
    for dep in list(payload.get("dependencies", [])) + list(enrichment.get("dependencies", [])):
        deps.append(resolve_service_name(dep) or dep)
    known = _known_services()
    for match in DEP_RE.findall(text):
        name = resolve_service_name(match) or match.lower()
        deps.append(name)
    for name in known:
        if name != service and re.search(rf"\b{re.escape(name)}\b", text, re.I):
            deps.append(name)
    deps = sorted({d for d in deps if d and d != service})

    deployments = sorted({f"{svc.lower()} v{ver}" for svc, ver in VERSION_RE.findall(text)})
    if payload.get("deployment"):
        deployments = sorted(set(deployments) | {str(payload["deployment"])})

    error_types = sorted(name for name, pattern in ERROR_TYPES.items() if re.search(pattern, text, re.I))

    return {
        "service": service,
        "environment": incident.get("environment") or payload.get("environment", ""),
        "dependencies": deps,
        "deployments": deployments,
        "error_types": error_types,
        "symptom": str(payload.get("alert") or payload.get("details") or payload.get("alarm_name")
                       or payload.get("reason") or "")[:200],
        "timestamp": payload.get("last_seen_at") or incident.get("event_time") or incident.get("created_at"),
    }


def build_recall_query(entities: Dict[str, Any]) -> str:
    """A full-sentence question, per the mind_query tool guidance: name the entities you expect."""
    parts = [f"Find past OnCallAI incidents involving {entities['service']}"]
    if entities["dependencies"]:
        parts.append(f"or its dependencies {', '.join(entities['dependencies'])}")
    if entities["deployments"]:
        parts.append(f"around deployments {', '.join(entities['deployments'])}")
    if entities["error_types"]:
        parts.append(f"with failures like {', '.join(e.replace('_', ' ') for e in entities['error_types'])}")
    parts.append("and list each incident's root cause and mitigation")
    return " ".join(parts) + "."
