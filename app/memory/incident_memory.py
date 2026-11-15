"""MIND as persistent incident memory for OnCallAI.

Three public functions:
  recall_history(incident, collected)          -> what MIND knows that relates to this incident
  apply_incident_memory(incident, collected, analysis) -> analysis + historical hypotheses (with provenance)
  remember_resolution(incident, resolution)    -> write the confirmed RCA back, deduplicated

Rules this module follows:
  * MIND never blocks the workflow. Every failure returns a status, never raises.
  * History is a hypothesis, not an answer. It only influences the RCA when the
    current logs corroborate it (shared failure signature + a service/dependency link).
  * Provenance is explicit: current-log evidence and historical evidence are kept apart.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List

from app.db import dal
from app.memory import config, telemetry
from app.memory.entities import build_recall_query, extract_entities
from app.memory.mind_client import MindClient, MindResponseError, MindUnavailable

KEY_RE = re.compile(r"OnCallAI-Incident-Key:\s*(oncallai-[a-f0-9]{12})")
RECORD_RE = re.compile(r"OnCallAI-Record:\s*(\{.*?\})\s*(?:$|\n)", re.M)
REQUIRED_RECORD_FIELDS = ("key", "service", "root_cause")


# --------------------------------------------------------------------------
# client wiring (tests patch get_client to return a FakeMind)
# --------------------------------------------------------------------------
def get_client():
    if not config.mind_enabled():
        return None
    import os
    return MindClient(os.environ["MIND_API_KEY"], config.MIND_BASE_URL, config.MIND_TIMEOUT_SECONDS)


def memory_key(incident_id: str) -> str:
    return "oncallai-" + hashlib.sha256(str(incident_id).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------
# recall
# --------------------------------------------------------------------------
def _parse_records(text: str) -> tuple[List[Dict[str, Any]], int]:
    records, bad = [], 0
    for raw in RECORD_RE.findall(text or ""):
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            bad += 1
            continue
        if not isinstance(rec, dict) or not all(rec.get(f) for f in REQUIRED_RECORD_FIELDS):
            bad += 1
            continue
        records.append(rec)
    return records, bad


def _relevance(rec: Dict[str, Any], entities: Dict[str, Any]) -> tuple[int, List[str]]:
    reasons: List[str] = []
    score = 0
    svc = entities["service"]
    rec_services = {rec.get("service"), rec.get("affected_component"), *rec.get("dependencies", [])} - {None, ""}
    if rec.get("service") == svc:
        score += 3
        reasons.append(f"same service ({svc})")
    elif svc in rec_services:
        score += 2
        reasons.append(f"{svc} appears in that incident's dependency path")
    shared_deps = set(entities["dependencies"]) & rec_services
    if shared_deps:
        score += 2
        reasons.append(f"shared dependency: {', '.join(sorted(shared_deps))}")
    shared_err = set(entities["error_types"]) & set(rec.get("error_types", []))
    if shared_err:
        score += 1
        reasons.append(f"shared failure signature: {', '.join(sorted(shared_err))}")
    return score, reasons


def recall_history(incident: Dict[str, Any], collected: Dict[str, Any], client=None) -> Dict[str, Any]:
    client = client if client is not None else get_client()
    entities = extract_entities(incident, collected)
    result: Dict[str, Any] = {
        "status": "disabled", "items": [], "entities": entities, "query": None,
        "latency_ms": 0, "fallback_activated": False, "partial_records": 0, "mode": config.MIND_QUERY_MODE,
    }
    if client is None:
        return result

    query = build_recall_query(entities)
    result["query"] = query
    t0 = time.perf_counter()
    try:
        resp = client.query(query, mode=config.MIND_QUERY_MODE, retrieve_only=True,
                            max_context_tokens=config.MIND_MAX_CONTEXT_TOKENS)
    except (MindUnavailable, MindResponseError, Exception) as exc:  # noqa: BLE001 - never break triage
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        result["status"] = "malformed" if isinstance(exc, MindResponseError) else "unavailable"
        result["fallback_activated"] = True
        result["error"] = f"{type(exc).__name__}: {exc}"
        telemetry.emit("mind_query_failed", incident.get("id"), status=result["status"],
                       error=result["error"], latency_ms=result["latency_ms"])
        telemetry.emit("mind_fallback_activated", incident.get("id"), reason=result["status"])
        return result
    result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    text = "\n".join([resp.get("response") or "", *[str(s) for s in (resp.get("sources") or [])]])
    records, bad = _parse_records(text)
    # Graph modes may return entity/relationship context without the raw record line.
    # Hydrate any incident keys we saw but could not parse, via entry search.
    seen = {r["key"] for r in records}
    for key in [k for k in dict.fromkeys(KEY_RE.findall(text)) if k not in seen][: config.MIND_MAX_HISTORY]:
        try:
            for entry in client.search_entries(key, limit=3):
                recs, b = _parse_records(str(entry.get("content", "")))
                bad += b
                records.extend(r for r in recs if r["key"] == key)
        except Exception:  # noqa: BLE001
            bad += 1

    own_key = memory_key(incident.get("id", ""))
    candidates: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if rec["key"] != own_key and rec["key"] not in candidates:
            score, reasons = _relevance(rec, entities)
            candidates[rec["key"]] = {**rec, "relevance": score, "match_reasons": reasons, "source": "mind"}
    # Pass 1 needs a direct entity link, not just a matching error word.
    unique = {k: c for k, c in candidates.items() if c["relevance"] >= 2}
    # Pass 2 follows one relationship hop: services that accepted incidents point at.
    hop: Dict[str, str] = {}
    for k, c in unique.items():
        for node in {c.get("affected_component"), *c.get("dependencies", [])} - {None, "", entities["service"]}:
            hop.setdefault(node, k)
    for k, c in candidates.items():
        if k in unique:
            continue
        linked = {c.get("service"), c.get("affected_component")} & set(hop)
        if linked:
            node = sorted(linked)[0]
            c["relevance"] += 2
            c["match_reasons"].append(
                f"reached through {hop[node]}: {entities['service']} -> {node} -> this incident")
            unique[k] = c

    items = sorted(unique.values(), key=lambda r: r["relevance"], reverse=True)[: config.MIND_MAX_HISTORY]
    result["items"] = items
    result["partial_records"] = bad
    result["status"] = "ok" if items else "no_history"
    if bad and items:
        result["status"] = "partial"
    if not items and (resp.get("response") or "").strip():
        result["raw_context_excerpt"] = resp["response"].strip()[:400]
    telemetry.emit("mind_query_succeeded", incident.get("id"), status=result["status"],
                   latency_ms=result["latency_ms"], historical_incidents=len(items),
                   partial_records=bad, mode=config.MIND_QUERY_MODE)
    return result


# --------------------------------------------------------------------------
# merge into the RCA
# --------------------------------------------------------------------------
def apply_incident_memory(incident: Dict[str, Any], collected: Dict[str, Any],
                          analysis: Dict[str, Any], client=None) -> Dict[str, Any]:
    recall = recall_history(incident, collected, client=client)
    if recall["status"] == "disabled":
        return analysis

    current = recall["entities"]
    hypotheses = []
    used = False
    for item in recall["items"]:
        shared_err = sorted(set(current["error_types"]) & set(item.get("error_types", [])))
        only_past = sorted(set(item.get("error_types", [])) - set(current["error_types"]))
        only_now = sorted(set(current["error_types"]) - set(item.get("error_types", [])))
        corroborated = bool(shared_err)
        hypotheses.append({
            "memory_key": item["key"],
            "past_service": item.get("service"),
            "past_root_cause": item.get("root_cause"),
            "past_mitigation": item.get("mitigation", []),
            "match_reasons": item.get("match_reasons", []),
            "corroborated_by_current_logs": corroborated,
            "shared_signals": shared_err,
            "seen_only_in_past": only_past,
            "seen_only_now": only_now,
        })
        used = used or corroborated

    out = dict(analysis)
    out["provenance"] = {
        "current_logs": list(analysis.get("evidence", [])),
        "historical_mind": [
            f"{h['memory_key']}: {h['past_root_cause']} "
            f"({'corroborated' if h['corroborated_by_current_logs'] else 'NOT corroborated'} by current logs)"
            for h in hypotheses
        ],
    }
    if used:
        mitigations = list(out.get("mitigations", []))
        for h in hypotheses:
            if not h["corroborated_by_current_logs"]:
                continue
            for m in h["past_mitigation"]:
                candidate = f"Check: {m} (worked for {h['memory_key']})"
                if candidate not in mitigations:
                    mitigations.append(candidate)
        out["mitigations"] = mitigations
        # Confidence is left alone on purpose: history agreeing on a failure signal is not
        # evidence that the current root cause is right.
        if str(out.get("root_cause", "")).lower() == "inconclusive":
            lead = next(h for h in hypotheses if h["corroborated_by_current_logs"])
            out["root_cause"] = (f"Inconclusive from current logs alone. Strongest historical lead: "
                                 f"{lead['past_root_cause']} ({lead['memory_key']}). Needs confirmation.")

    out["historical_context"] = {
        "status": recall["status"], "mode": recall["mode"], "query": recall["query"],
        "latency_ms": recall["latency_ms"], "fallback_activated": recall["fallback_activated"],
        "historical_incidents": len(recall["items"]), "used_in_rca": used, "hypotheses": hypotheses,
        "partial_records": recall["partial_records"], "error": recall.get("error"),
    }
    dal.record_step(
        incident["id"], "memory", "recall",
        f"MIND {recall['status']}: {len(recall['items'])} related incidents, used_in_rca={used}",
        out["historical_context"],
        status="OK" if recall["status"] in {"ok", "no_history", "partial"} else "WARN",
    )
    telemetry.emit("mind_context_used" if used else "mind_context_not_used", incident.get("id"),
                   historical_incidents=len(recall["items"]))
    return out


# --------------------------------------------------------------------------
# write-back (deduplicated)
# --------------------------------------------------------------------------
LEDGER_SQL = """CREATE TABLE IF NOT EXISTS mind_memory_writes(
  incident_id TEXT PRIMARY KEY, memory_key TEXT NOT NULL, entry_id TEXT,
  status TEXT NOT NULL, content TEXT, written_at TEXT NOT NULL)"""


@contextmanager
def _ledger():
    con = sqlite3.connect(dal.DB_FILE)
    try:
        con.execute(LEDGER_SQL)
        yield con
        con.commit()
    finally:
        con.close()


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_memory(incident: Dict[str, Any], resolution: Dict[str, Any], entities: Dict[str, Any]) -> tuple[str, str, Dict[str, Any]]:
    """Natural-language sentences for graph extraction + one machine-readable line for exact recall."""
    key = memory_key(incident["id"])
    svc = entities["service"]
    component = resolution.get("affected_component") or svc
    deps = sorted(set(entities["dependencies"]) | set(resolution.get("dependencies", [])))
    deployment = resolution.get("deployment") or (entities["deployments"][0] if entities["deployments"] else "")
    mitigation = list(resolution.get("mitigation") or [])
    record = {
        "key": key, "service": svc, "environment": entities["environment"], "dependencies": deps,
        "affected_component": component, "deployment": deployment, "error_types": entities["error_types"],
        "symptom": entities["symptom"], "root_cause": resolution["root_cause"], "mitigation": mitigation,
        "confirmed_by": resolution.get("confirmed_by", "human"), "related_incidents": resolution.get("related_incidents", []),
        "resolved_at": resolution.get("resolved_at") or _now(),
    }
    lines = [f"OnCallAI incident on {svc} in {entities['environment'] or 'unknown environment'}: {entities['symptom']}."]
    for dep in deps:
        lines.append(f"{svc} depends on {dep}.")
    if component != svc:
        lines.append(f"The failing component was {component}, not {svc} itself.")
    if deployment:
        lines.append(f"The incident followed deployment {deployment}.")
    if entities["error_types"]:
        lines.append("Failure signals: " + ", ".join(e.replace("_", " ") for e in entities["error_types"]) + ".")
    lines.append(f"Root cause: {resolution['root_cause']}")
    if mitigation:
        lines.append("Mitigation that resolved it: " + "; ".join(mitigation) + ".")
    for rel in record["related_incidents"]:
        lines.append(f"Related to earlier incident {rel}.")
    lines.append(f"Resolved {record['resolved_at']}, root cause confirmed by {record['confirmed_by']}.")
    lines += ["", f"OnCallAI-Incident-Key: {key}", "OnCallAI-Record: " + json.dumps(record, sort_keys=True)]
    title = f"Incident on {svc} caused by {resolution['root_cause'][:60].rstrip('.')}"
    title = re.sub(r"[/()]", " ", title)  # MIND title rule: no slashes or parentheses
    return title, "\n".join(lines), record


def remember_resolution(incident: Dict[str, Any], resolution: Dict[str, Any],
                        collected: Dict[str, Any] | None = None, client=None) -> Dict[str, Any]:
    client = client if client is not None else get_client()
    if client is None:
        return {"status": "disabled"}
    key = memory_key(incident["id"])

    with _ledger() as con:
        row = con.execute("SELECT status, entry_id FROM mind_memory_writes WHERE incident_id=?",
                          (incident["id"],)).fetchone()
    if row and row[0] == "WRITTEN":
        telemetry.emit("mind_writeback_skipped_duplicate", incident["id"], memory_key=key, via="ledger")
        return {"status": "duplicate_skipped", "memory_key": key, "entry_id": row[1]}

    try:  # second guard: another worker or a lost ledger may have written it already
        for entry in client.search_entries(key, limit=3):
            if key in str(entry.get("content", "")):
                eid = entry.get("entry_id") or entry.get("id")
                with _ledger() as con:
                    con.execute("INSERT OR REPLACE INTO mind_memory_writes VALUES(?,?,?,?,?,?)",
                                (incident["id"], key, eid, "WRITTEN", None, _now()))
                telemetry.emit("mind_writeback_skipped_duplicate", incident["id"], memory_key=key, via="mind_search")
                return {"status": "duplicate_skipped", "memory_key": key, "entry_id": eid}
    except Exception:  # noqa: BLE001 - search is best-effort, the ledger already guards
        pass

    entities = extract_entities(incident, collected or {})
    title, content, record = render_memory(incident, resolution, entities)
    try:
        created = client.create_entry(title=title, content=content, folder=config.MIND_FOLDER,
                                      tags=["oncallai", "incident", entities["service"], key])
    except Exception as exc:  # noqa: BLE001
        with _ledger() as con:
            con.execute("INSERT OR REPLACE INTO mind_memory_writes VALUES(?,?,?,?,?,?)",
                        (incident["id"], key, None, "PENDING", json.dumps({"title": title, "content": content}), _now()))
        telemetry.emit("mind_writeback_failed", incident["id"], memory_key=key, error=f"{type(exc).__name__}: {exc}")
        return {"status": "failed_queued", "memory_key": key, "error": str(exc)}

    eid = created.get("entry_id") or created.get("id")
    with _ledger() as con:
        con.execute("INSERT OR REPLACE INTO mind_memory_writes VALUES(?,?,?,?,?,?)",
                    (incident["id"], key, eid, "WRITTEN", None, _now()))
    telemetry.emit("mind_writeback_succeeded", incident["id"], memory_key=key, entry_id=eid)
    return {"status": "written", "memory_key": key, "entry_id": eid, "record": record, "title": title}


def retry_pending_writes(client=None) -> int:
    client = client if client is not None else get_client()
    if client is None:
        return 0
    with _ledger() as con:
        rows = con.execute("SELECT incident_id, memory_key, content FROM mind_memory_writes WHERE status='PENDING'").fetchall()
    done = 0
    for incident_id, key, payload in rows:
        body = json.loads(payload)
        try:
            created = client.create_entry(title=body["title"], content=body["content"], folder=config.MIND_FOLDER,
                                          tags=["oncallai", "incident"])
        except Exception:  # noqa: BLE001
            continue
        with _ledger() as con:
            con.execute("UPDATE mind_memory_writes SET status='WRITTEN', entry_id=?, content=NULL WHERE incident_id=?",
                        (created.get("entry_id") or created.get("id"), incident_id))
        done += 1
    return done


def resolve_and_remember(incident_id: str, root_cause: str, mitigation: List[str], *,
                         affected_component: str | None = None, deployment: str | None = None,
                         related_incidents: List[str] | None = None, confirmed_by: str = "human",
                         logs: List[str] | None = None, client=None) -> Dict[str, Any]:
    """The resolution step: mark resolved locally, then write the confirmed RCA to MIND."""
    incident = dal.get_incident(incident_id)
    if incident is None:
        raise ValueError(f"unknown incident {incident_id}")
    dal.mark_incident_resolved(incident_id)
    result = remember_resolution(
        incident,
        {"root_cause": root_cause, "mitigation": mitigation, "affected_component": affected_component,
         "deployment": deployment, "related_incidents": related_incidents or [], "confirmed_by": confirmed_by},
        collected={"logs": logs or []}, client=client,
    )
    dal.record_step(incident_id, "memory", "writeback", f"MIND write-back: {result['status']}",
                    {k: v for k, v in result.items() if k != "record"},
                    status="OK" if result["status"] in {"written", "duplicate_skipped", "disabled"} else "WARN")
    return result
