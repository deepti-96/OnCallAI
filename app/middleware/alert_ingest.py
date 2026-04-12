import json
from pathlib import Path
from typing import Any, Dict

from app.db.dal import init_db, record_incident
from app.middleware.alert_normalizer import normalize_cloudwatch_alarm


def ingest_cloudwatch_alert(alert: Dict[str, Any]) -> str:
    normalized = normalize_cloudwatch_alarm(alert)
    init_db()
    return record_incident(**normalized)


def ingest_cloudwatch_alert_file(path: str) -> str:
    alert = json.loads(Path(path).read_text(encoding="utf-8"))
    return ingest_cloudwatch_alert(alert)
