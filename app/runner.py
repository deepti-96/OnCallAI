# app/runner.py
import os
import time
import traceback

from app.agents.analyst_agent import analyze_logs
from app.agents.collector_agent import collector_run
from app.agents.supervisor import supervisor_orchestrate
from app.db.dal import (
    claim_next_queued_incident,
    complete_queued_incident,
    init_db,
    mark_failed,
    mark_in_progress,
    mark_done,
    sync_open_incidents_to_queue,
    record_step,
)

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

def process_incident(inc: dict):
    iid = inc["id"]
    try:
        payload = inc.get("payload") or {}
        if str(payload.get("state", "")).upper() == "OK": #2 types of Cloudwatch alerts: "OK" and "ALARM"
            record_step(
                iid,
                "supervisor",
                "skip",
                "Skipping analysis because alert is already in a recovered state",
                {"state": payload.get("state")},
                status="OK",
            )
            mark_done(iid)
            complete_queued_incident(iid, status="DONE")
            return

        mark_in_progress(iid)
        record_step(iid, "supervisor", "dispatch", "Dispatching incident to collector", status="STARTED")

        collected = collector_run(inc)
        analysis = analyze_logs(inc, collected)
        supervisor_orchestrate(inc, analysis)
        complete_queued_incident(iid, status="DONE")
    except Exception as e:
        record_step(iid, "supervisor", "error", f"{e}", {"trace": traceback.format_exc()}, status="ERROR")
        mark_failed(iid)
        complete_queued_incident(iid, status="FAILED", error=str(e))

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
