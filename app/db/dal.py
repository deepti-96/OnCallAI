# app/db/dal.py
import datetime
import json
import os
import pathlib
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from app.models.escalation_policy import compute_escalation_guidance

try:
    from dotenv import load_dotenv
except ImportError:  # Optional during lightweight local runs
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

DB_FILE = os.environ.get("DB_FILE", "dev.db")
SCHEMA_FILE = pathlib.Path(__file__).with_name("schema.sql")

def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
    except ValueError:
        return None

def _conn(rowdict: bool = False) -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys = ON")
    if rowdict:
        con.row_factory = sqlite3.Row
    return con


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _ensure_column(con: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column in _table_columns(con, table):
        return
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _decode_payload(row: sqlite3.Row | Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
    if not row:
        return None

    data = dict(row)
    payload_json = data.pop("payload_json", None)
    try:
        data["payload"] = json.loads(payload_json or "{}")
    except Exception:
        data["payload"] = {}
    return data


def _incident_summary(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = _decode_payload(row) or {}
    payload = data.get("payload") or {}
    enrichment = payload.get("enrichment") or {}
    event_time = _parse_iso(data.get("event_time") or data.get("created_at"))
    ingested_at = _parse_iso(data.get("ingested_at"))
    processed_at = _parse_iso(data.get("processed_at"))
    completed_at = _parse_iso(data.get("completed_at"))
    last_seen_at = _parse_iso(payload.get("last_seen_at"))
    reference_ts = last_seen_at or event_time or ingested_at
    age_minutes = None
    if reference_ts is not None:
        delta = datetime.datetime.now(datetime.UTC) - reference_ts
        age_minutes = max(int(delta.total_seconds() // 60), 0)

    data["source"] = payload.get("source", "manual")
    data["alert_type"] = payload.get("alert_type", "incident")
    data["alert_state"] = payload.get("state", "")
    data["alarm_name"] = payload.get("alarm_name", "")
    data["region"] = payload.get("region", "")
    data["occurrence_count"] = int(payload.get("occurrence_count", 1) or 1)
    data["last_seen_at"] = payload.get("last_seen_at", data.get("created_at"))
    data["event_time"] = data.get("event_time") or data.get("created_at")
    data["ingested_at"] = data.get("ingested_at")
    data["processed_at"] = data.get("processed_at")
    data["completed_at"] = data.get("completed_at")
    data["owner_team"] = enrichment.get("owner_team", "")
    data["age_minutes"] = age_minutes
    escalation = compute_escalation_guidance(data)
    data["escalation_priority"] = escalation["priority"]
    data["escalation_target"] = escalation["target"]
    data["escalation_reason"] = escalation["reason"]
    data["should_page"] = escalation["should_page"]
    return data


def _enrich_incident_record(row: sqlite3.Row | Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return _incident_summary(row)

def init_db() -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with _conn() as con:
        con.executescript(sql)
        _ensure_column(con, "incidents", "dedupe_key", "TEXT")
        _ensure_column(con, "incidents", "event_time", "TEXT")
        _ensure_column(con, "incidents", "ingested_at", "TEXT")
        _ensure_column(con, "incidents", "processed_at", "TEXT")
        _ensure_column(con, "incidents", "completed_at", "TEXT")
        _ensure_column(con, "incident_queue", "dead_letter_at", "TEXT")

# ---------- writes ----------

def record_incident(
    status: str,                 # "OPEN" | "IN_PROGRESS" | "DONE" | "FAILED"
    service: str,
    environment: str,
    severity: str,
    payload: Dict[str, Any] | None = None,
    created_at: str | None = None,
    event_time: str | None = None,
    ingested_at: str | None = None,
    processed_at: str | None = None,
    completed_at: str | None = None,
    incident_id: str | None = None
) -> str:
    """Insert a new incident and return its id."""
    incident_id = incident_id or str(uuid.uuid4())
    dedupe_key = (payload or {}).get("dedupe_key")
    event_time = event_time or created_at or _now_iso()
    ingested_at = ingested_at or _now_iso()
    with _conn() as con:
        con.execute(
            """INSERT INTO incidents(
                 id, status, service, environment, severity, dedupe_key,
                 payload_json, created_at, event_time, ingested_at, processed_at, completed_at
               )
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                incident_id,
                status,
                service,
                environment,
                severity,
                dedupe_key,
                json.dumps(payload or {}),
                event_time,
                event_time,
                ingested_at,
                processed_at,
                completed_at,
            ),
        )
        return incident_id


def update_incident(
    incident_id: str,
    *,
    status: str | None = None,
    severity: str | None = None,
    payload: Dict[str, Any] | None = None,
    created_at: str | None = None,
    event_time: str | None = None,
    ingested_at: str | None = None,
    processed_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    dedupe_key = (payload or {}).get("dedupe_key") if payload is not None else None

    if status is not None:
        updates.append("status=?")
        params.append(status)
    if severity is not None:
        updates.append("severity=?")
        params.append(severity)
    if payload is not None:
        updates.append("dedupe_key=?")
        params.append(dedupe_key)
    if payload is not None:
        updates.append("payload_json=?")
        params.append(json.dumps(payload))
    if created_at is not None:
        updates.append("created_at=?")
        params.append(created_at)
    if event_time is not None:
        updates.append("event_time=?")
        params.append(event_time)
    if ingested_at is not None:
        updates.append("ingested_at=?")
        params.append(ingested_at)
    if processed_at is not None:
        updates.append("processed_at=?")
        params.append(processed_at)
    if completed_at is not None:
        updates.append("completed_at=?")
        params.append(completed_at)

    if not updates:
        return

    params.append(incident_id)
    with _conn() as con:
        con.execute(f"UPDATE incidents SET {', '.join(updates)} WHERE id=?", tuple(params))

def record_step(
    incident_id: str, agent: str, phase: str, message: str,
    data: Dict[str, Any] | None = None, status: str | None = None
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO agent_steps(incident_id, agent, phase, message, data_json, ts, status)
               VALUES(?,?,?,?,?,?,?)""",
            (incident_id, agent, phase, message, json.dumps(data or {}), _now_iso(), status)
        )

def save_report(incident_id: str, report_json: Dict[str, Any], report_md: str) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO reports(incident_id, report_json, report_md, created_at)
               VALUES(?,?,?,?)""",
            (incident_id, json.dumps(report_json), report_md, _now_iso())
        )

# ---------- reads (for UI) ----------

def list_incidents(limit: int = 200) -> List[Dict[str, Any]]:
    sql = """SELECT id, status, service, environment, severity, payload_json, created_at,
                    event_time, ingested_at, processed_at, completed_at, dedupe_key
             FROM incidents ORDER BY created_at DESC, id DESC LIMIT ?"""
    with _conn(rowdict=True) as con:
        rows = con.execute(sql, (limit,)).fetchall()
    return [_incident_summary(r) for r in rows]

def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    with _conn(rowdict=True) as con:
        r = con.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
    return _enrich_incident_record(r)

def list_steps(incident_id: str) -> List[Dict[str, Any]]:
    sql = """SELECT id, agent, phase, status, message, ts, data_json
             FROM agent_steps WHERE incident_id=? ORDER BY id ASC"""
    with _conn(rowdict=True) as con:
        rows = con.execute(sql, (incident_id,)).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d.pop("data_json") or "{}")
        except Exception:
            d["data"] = {}
        out.append(d)
    return out

def get_latest_report(incident_id: str) -> Optional[Dict[str, Any]]:
    sql = """SELECT id, report_json, report_md, created_at
             FROM reports WHERE incident_id=? ORDER BY id DESC LIMIT 1"""
    with _conn(rowdict=True) as con:
        r = con.execute(sql, (incident_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["report"] = json.loads(d.pop("report_json") or "{}")
    except Exception:
        d["report"] = {}
    return d


def enqueue_incident(incident_id: str) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO incident_queue(incident_id, status, enqueued_at, claimed_at, completed_at, attempts, last_error)
               VALUES (?, 'PENDING', ?, NULL, NULL, 0, NULL)
               ON CONFLICT(incident_id) DO UPDATE SET
                 status='PENDING',
                 enqueued_at=excluded.enqueued_at,
                 claimed_at=NULL,
                 completed_at=NULL,
                 last_error=NULL
               WHERE incident_queue.status IN ('DONE', 'FAILED')""",
            (incident_id, _now_iso()),
        )


def sync_open_incidents_to_queue() -> int:
    queued = 0
    for incident in get_open_incidents():
        enqueue_incident(incident["id"])
        queued += 1
    return queued


def claim_next_queued_incident() -> Optional[Dict[str, Any]]:
    with _conn(rowdict=True) as con:
        queue_row = con.execute(
            """SELECT incident_id, attempts, enqueued_at
               FROM incident_queue
               WHERE status='PENDING'
               ORDER BY enqueued_at ASC, incident_id ASC
               LIMIT 1"""
        ).fetchone()
        if not queue_row:
            return None

        claimed_at = _now_iso()
        updated = con.execute(
            """UPDATE incident_queue
               SET status='IN_PROGRESS', claimed_at=?, attempts=attempts + 1
               WHERE incident_id=? AND status='PENDING'""",
            (claimed_at, queue_row["incident_id"]),
        )
        if updated.rowcount != 1:
            return None

        incident = con.execute(
            """SELECT id, status, service, environment, severity, dedupe_key, payload_json, created_at,
                     event_time, ingested_at, processed_at, completed_at
               FROM incidents
               WHERE id=?""",
            (queue_row["incident_id"],),
        ).fetchone()
    result = _enrich_incident_record(incident) or {}
    result["queue_attempts"] = int(queue_row["attempts"])
    result["queue_enqueued_at"] = queue_row["enqueued_at"]
    result["queue_claimed_at"] = claimed_at
    return result


def complete_queued_incident(incident_id: str, *, status: str = "DONE", error: str | None = None) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE incident_queue
               SET status=?, completed_at=?, dead_letter_at=?, last_error=?
               WHERE incident_id=?""",
            (
                status,
                _now_iso(),
                _now_iso() if status == "DEAD_LETTER" else None,
                error,
                incident_id,
            ),
        )


def requeue_queued_incident(incident_id: str, error: str | None = None) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE incident_queue
               SET status='PENDING',
                   claimed_at=NULL,
                   completed_at=NULL,
                   dead_letter_at=NULL,
                   last_error=?
               WHERE incident_id=?""",
            (error, incident_id),
        )


def dead_letter_queued_incident(incident_id: str, error: str | None = None) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE incident_queue
               SET status='DEAD_LETTER',
                   completed_at=?,
                   dead_letter_at=?,
                   last_error=?
               WHERE incident_id=?""",
            (_now_iso(), _now_iso(), error, incident_id),
        )


def find_open_incident_by_dedupe_key(dedupe_key: str) -> Optional[Dict[str, Any]]:
    if not dedupe_key:
        return None
    with _conn(rowdict=True) as con:
        row = con.execute(
            """SELECT id, status, service, environment, severity, dedupe_key, payload_json, created_at
               FROM incidents
               WHERE status='OPEN' AND dedupe_key=?
               ORDER BY created_at ASC, id ASC
               LIMIT 1""",
            (dedupe_key,),
        ).fetchone()
    return _enrich_incident_record(row)

# ---------- helpers for the agent loop ----------

def get_open_incidents() -> List[Dict[str, Any]]:
    with _conn(rowdict=True) as con:
        rows = con.execute(
            "SELECT * FROM incidents WHERE status='OPEN' ORDER BY created_at ASC, id ASC"
        ).fetchall()
    return [_enrich_incident_record(r) for r in rows]

def mark_in_progress(incident_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE incidents SET status='IN_PROGRESS', processed_at=? WHERE id=?",
            (_now_iso(), incident_id),
        )

def mark_done(incident_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE incidents SET status='DONE', completed_at=? WHERE id=?",
            (_now_iso(), incident_id),
        )

def mark_failed(incident_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE incidents SET status='FAILED', completed_at=? WHERE id=?",
            (_now_iso(), incident_id),
        )

def mark_open(incident_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE incidents SET status='OPEN' WHERE id=?",
            (incident_id,),
        )
