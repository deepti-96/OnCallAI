from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.models.service_registry import get_service_enrichment, normalize_service_name, resolve_service_name

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

FOLDER_KEYWORDS = {
    "db": ("db", "database", "sql", "postgres", "mysql", "query", "connection"),
    "infra": ("cpu", "oom", "infra", "memory", "node", "host", "latency", "timeout"),
    "web": ("http", "api", "web", "frontend", "request", "route"),
}

SEVERITY_WINDOW_MINUTES = {
    "CRITICAL": 60,
    "HIGH": 30,
    "MEDIUM": 15,
}


def _tokenize(value: str | None) -> List[str]:
    if not value:
        return []
    return [token.lower() for token in TOKEN_RE.findall(value)]


def _dedupe_terms(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    terms: List[str] = []
    for value in values:
        term = value.strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _choose_folder(corpus: str) -> str:
    for folder, keywords in FOLDER_KEYWORDS.items():
        if any(keyword in corpus for keyword in keywords):
            return folder
    return "web"


def build_log_collection_profile(incident: Dict[str, Any]) -> Dict[str, Any]:
    payload = incident.get("payload") or {}
    original_service = incident.get("service") or ""
    service = resolve_service_name(original_service)
    if not service:
        service = normalize_service_name(original_service or "unknown-service")
    severity = str(incident.get("severity") or "LOW").upper()
    enrichment = get_service_enrichment(service, incident.get("environment"), requested_service=original_service)

    service_aliases = enrichment.get("aliases") or enrichment.get("service_aliases") or []
    if not isinstance(service_aliases, list):
        service_aliases = [str(service_aliases)]

    signal_parts = [
        service,
        incident.get("environment", ""),
        severity,
        incident.get("alert_type", ""),
        payload.get("alert_type", ""),
        payload.get("alert", ""),
        payload.get("source", ""),
        payload.get("details", ""),
        payload.get("state", ""),
        enrichment.get("owner_team", ""),
        enrichment.get("primary_contact", ""),
        enrichment.get("recent_deploy_hint", ""),
        " ".join(service_aliases),
    ]
    corpus = " ".join(str(part) for part in signal_parts if part).lower()
    folder = _choose_folder(corpus)
    time_window_minutes = SEVERITY_WINDOW_MINUTES.get(severity, 10)

    search_terms = _dedupe_terms(
        [service.lower()]
        + _tokenize(service)
        + _tokenize(incident.get("environment"))
        + _tokenize(payload.get("alert_type"))
        + _tokenize(payload.get("alert"))
        + _tokenize(payload.get("source"))
        + _tokenize(payload.get("details"))
        + _tokenize(payload.get("state"))
        + _tokenize(enrichment.get("owner_team"))
        + _tokenize(enrichment.get("primary_contact"))
        + _tokenize(enrichment.get("recent_deploy_hint"))
        + [alias for alias in service_aliases if isinstance(alias, str)]
    )[:12]

    reason = (
        f"Selected {folder} logs for {service} using severity {severity} "
        f"and service context from the catalog"
    )

    return {
        "service": service,
        "severity": severity,
        "environment": incident.get("environment", "prod"),
        "folder": folder,
        "search_terms": search_terms,
        "time_window_minutes": time_window_minutes,
        "reason": reason,
        "catalog": enrichment,
    }


def _score_log_text(text: str, search_terms: List[str]) -> int:
    lower_text = text.lower()
    score = 0
    for term in search_terms:
        if len(term) < 3:
            continue
        score += lower_text.count(term)
    if any(token in lower_text for token in ("error", "exception", "timeout", "refused", "failed")):
        score += 2
    return score


def collect_logs_for_incident(
    incident: Dict[str, Any],
    *,
    root: str,
    limit: int = 5,
) -> Dict[str, Any]:
    profile = build_log_collection_profile(incident)
    folder_path = Path(root) / profile["folder"]
    candidates: List[dict[str, Any]] = []

    if folder_path.exists():
        for log_file in sorted(folder_path.glob("*.log")):
            try:
                text = log_file.read_text(encoding="utf-8", errors="ignore")[:8000]
            except OSError:
                continue
            candidates.append(
                {
                    "path": str(log_file),
                    "score": _score_log_text(text, profile["search_terms"]),
                    "content": text[:5000],
                }
            )

    candidates.sort(key=lambda item: (-item["score"], item["path"]))
    selected = candidates[:limit]

    return {
        "folder": profile["folder"],
        "logs": [item["content"] for item in selected],
        "selected_files": [item["path"] for item in selected],
        "profile": profile,
    }
