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
    created_at = _parse_iso(data.get("created_at"))
    last_seen_at = _parse_iso(payload.get("last_seen_at"))
    reference_ts = last_seen_at or created_at
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

# ---------- writes ----------

def record_incident(
    status: str,                 # "OPEN" | "IN_PROGRESS" | "DONE" | "FAILED"
    service: str,
    environment: str,
    severity: str,
    payload: Dict[str, Any] | None = None,
    created_at: str | None = None,
    incident_id: str | None = None
) -> int:
    """Insert a new incident and return its id."""
    incident_id = incident_id or str(uuid.uuid4())
    with _conn() as con:
        con.execute(
            """INSERT INTO incidents(id, status, service, environment, severity, payload_json, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                incident_id,
                status,
                service,
                environment,
                severity,
                json.dumps(payload or {}),
                created_at or _now_iso(),
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
) -> None:
    updates: list[str] = []
    params: list[Any] = []

    if status is not None:
        updates.append("status=?")
        params.append(status)
    if severity is not None:
        updates.append("severity=?")
        params.append(severity)
    if payload is not None:
        updates.append("payload_json=?")
        params.append(json.dumps(payload))
    if created_at is not None:
        updates.append("created_at=?")
        params.append(created_at)

    if not updates:
        return

    params.append(incident_id)
    with _conn() as con:
        con.execute(f"UPDATE incidents SET {', '.join(updates)} WHERE id=?", tuple(params))

def record_step(
    incident_id: int, agent: str, phase: str, message: str,
    data: Dict[str, Any] | None = None, status: str | None = None
) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO agent_steps(incident_id, agent, phase, message, data_json, ts, status)
               VALUES(?,?,?,?,?,?,?)""",
            (incident_id, agent, phase, message, json.dumps(data or {}), _now_iso(), status)
        )

def save_report(incident_id: int, report_json: Dict[str, Any], report_md: str) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO reports(incident_id, report_json, report_md, created_at)
               VALUES(?,?,?,?)""",
            (incident_id, json.dumps(report_json), report_md, _now_iso())
        )

# ---------- reads (for UI) ----------

def list_incidents(limit: int = 200) -> List[Dict[str, Any]]:
    sql = """SELECT id, status, service, environment, severity, payload_json, created_at
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

# ---------- helpers for the agent loop ----------

def get_open_incidents() -> List[Dict[str, Any]]:
    with _conn(rowdict=True) as con:
        rows = con.execute(
            "SELECT * FROM incidents WHERE status='OPEN' ORDER BY created_at ASC, id ASC"
        ).fetchall()
    return [_enrich_incident_record(r) for r in rows]

def mark_in_progress(incident_id: str) -> None:
    with _conn() as con:
        con.execute("UPDATE incidents SET status='IN_PROGRESS' WHERE id=?", (incident_id,))

def mark_done(incident_id: str) -> None:
    with _conn() as con:
        con.execute("UPDATE incidents SET status='DONE' WHERE id=?", (incident_id,))

def mark_failed(incident_id: str) -> None:
    with _conn() as con:
        con.execute("UPDATE incidents SET status='FAILED' WHERE id=?", (incident_id,))
