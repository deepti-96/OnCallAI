import json
import os
import sqlite3
import time
import traceback

from app.agents.analyst_agent import analyze_logs
from app.agents.collector_agent import collector_run
from app.agents.supervisor import supervisor_orchestrate
from app.errors import RetryableIncidentError, TerminalIncidentError
from app.db.dal import (
    claim_next_queued_incident,
    complete_queued_incident,
    dead_letter_queued_incident,
    init_db,
    mark_failed,
    mark_in_progress,
    mark_done,
    mark_open,
    requeue_queued_incident,
    sync_open_incidents_to_queue,
    record_step,
)

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
MAX_INCIDENT_RETRIES = int(os.getenv("MAX_INCIDENT_RETRIES", "3"))


def _log_event(event: str, inc: dict, **fields) -> None:
    record = {
        "event": event,
        "incident_id": inc.get("id"),
        "service": inc.get("service"),
        "severity": inc.get("severity"),
        "queue_attempts": inc.get("queue_attempts", 0),
    }
    record.update(fields)
    print(json.dumps(record, sort_keys=True))


def _run_incident_pipeline(inc: dict) -> None:
    payload = inc.get("payload") or {}
    if str(payload.get("state", "")).upper() == "OK": #2 types of Cloudwatch alerts: "OK" and "ALARM"
        record_step(
            inc["id"],
            "supervisor",
            "skip",
            "Skipping analysis because alert is already in a recovered state",
            {"state": payload.get("state")},
            status="OK",
        )
        mark_done(inc["id"])
        complete_queued_incident(inc["id"], status="DONE")
        _log_event("incident_completed", inc, outcome="recovered")
        return

    mark_in_progress(inc["id"])
    record_step(inc["id"], "supervisor", "dispatch", "Dispatching incident to collector", status="STARTED")

    collected = collector_run(inc)
    analysis = analyze_logs(inc, collected)
    supervisor_orchestrate(inc, analysis)
    complete_queued_incident(inc["id"], status="DONE")
    _log_event("incident_completed", inc, outcome="processed")


def _dead_letter_incident(inc: dict, exc: Exception) -> None:
    message = f"{type(exc).__name__}: {exc}"
    record_step(
        inc["id"],
        "supervisor",
        "error",
        message,
        {"trace": traceback.format_exc(), "exception_type": type(exc).__name__},
        status="ERROR",
    )
    mark_failed(inc["id"])
    dead_letter_queued_incident(inc["id"], error=message)
    _log_event("incident_dead_lettered", inc, error=message, retryable=False)


def _retry_incident(inc: dict, exc: Exception) -> None:
    message = f"{type(exc).__name__}: {exc}"
    record_step(
        inc["id"],
        "supervisor",
        "retry",
        f"Retrying incident after transient failure: {message}",
        {"trace": traceback.format_exc(), "exception_type": type(exc).__name__},
        status="WARN",
    )
    mark_open(inc["id"])
    requeue_queued_incident(inc["id"], error=message)
    _log_event("incident_requeued", inc, error=message, retryable=True)


def process_incident(inc: dict):
    try:
        _run_incident_pipeline(inc)
    except RetryableIncidentError as exc:
        if int(inc.get("queue_attempts", 0) or 0) < MAX_INCIDENT_RETRIES:
            _retry_incident(inc, exc)
            return
        _dead_letter_incident(inc, exc)
    except TerminalIncidentError as exc:
        _dead_letter_incident(inc, exc)
    except (sqlite3.OperationalError, FileNotFoundError, TimeoutError) as exc:
        retryable_exc = RetryableIncidentError(str(exc))
        if int(inc.get("queue_attempts", 0) or 0) < MAX_INCIDENT_RETRIES:
            _retry_incident(inc, retryable_exc)
            return
        _dead_letter_incident(inc, retryable_exc)
    except Exception as exc:
        _dead_letter_incident(inc, exc)

def main():
    init_db()  # ensure tables exist
    sync_open_incidents_to_queue()
    print(f"[runner] polling every {POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            incident = claim_next_queued_incident()
            if incident is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            print(f"[runner] processing incident {incident['id']}")
            process_incident(incident)
        except Exception as e:
            print("[runner] loop error:", e)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
