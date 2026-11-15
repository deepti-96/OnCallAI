from __future__ import annotations

import collections
import re
import threading
from pathlib import Path
from typing import Any, Dict, List

from app.middleware.alert_ingest import _apply_enrichment
from app.middleware.alert_normalizer import normalize_cloudwatch_alarm
from app.middleware.log_collection import build_log_collection_profile

# Recent fetched log lines, for the console's log panel.
RECENT_LINES: collections.deque = collections.deque(maxlen=300)
_LOCK = threading.Lock()


def remember_lines(source: str, service: str, lines: List[Dict[str, Any]]) -> None:
    with _LOCK:
        for line in lines:
            RECENT_LINES.append(dict(line, source=source, service=line.get("service") or service))


def recent_lines(limit: int = 80) -> List[Dict[str, Any]]:
    with _LOCK:
        return list(RECENT_LINES)[-limit:]


def preview_incident(alert: Dict[str, Any]) -> Dict[str, Any]:
    """What ingest_cloudwatch_alert will store, without storing it. Lets us pick the log folder first."""
    normalized = _apply_enrichment(normalize_cloudwatch_alarm(alert))
    return {"id": "preview", **normalized}


def write_incident_logs(logs_root: str, alert: Dict[str, Any], lines: List[Dict[str, Any]], prefix: str) -> Path | None:
    """Write fetched lines into the folder the existing collector will choose for this alert.

    Done before the incident is enqueued, so the worker never races an empty log file.
    """
    if not lines:
        return None
    incident = preview_incident(alert)
    profile = build_log_collection_profile(incident)
    folder = Path(logs_root) / profile["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    key = (incident.get("payload") or {}).get("dedupe_key", "x")
    safe_service = re.sub(r"[^a-z0-9-]", "-", profile["service"].lower())
    path = folder / f"{prefix}-{safe_service}-{key}.log"
    text = "\n".join(f"{l['time']} {l.get('origin', '')} {l['message']}".replace("  ", " ") for l in lines)
    path.write_text(text + "\n", encoding="utf-8")
    return path
