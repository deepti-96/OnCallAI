# app/runner.py
import os
import time
import traceback

from app.agents.analyst_agent import analyze_logs
from app.agents.collector_agent import collector_run
from app.agents.supervisor import supervisor_orchestrate
from app.db.dal import (
    get_open_incidents,
    init_db,
    mark_failed,
    mark_in_progress,
    mark_done,
    record_step,
)

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

def process_incident(inc: dict):
    iid = inc["id"]
    try:
        payload = inc.get("payload") or {}
        if str(payload.get("state", "")).upper() == "OK":
            record_step(
                iid,
                "supervisor",
                "skip",
                "Skipping analysis because alert is already in a recovered state",
                {"state": payload.get("state")},
                status="OK",
            )
            mark_done(iid)
            return

        mark_in_progress(iid)
        record_step(iid, "supervisor", "dispatch", "Dispatching incident to collector", status="STARTED")

        collected = collector_run(inc)
        analysis = analyze_logs(inc, collected)
        supervisor_orchestrate(inc, analysis)
    except Exception as e:
        record_step(iid, "supervisor", "error", f"{e}", {"trace": traceback.format_exc()}, status="ERROR")
        mark_failed(iid)

def main():
    init_db()  # ensure tables exist
    print(f"[runner] polling every {POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            open_list = get_open_incidents()
            for inc in open_list:
                print(f"[runner] processing incident {inc['id']}")
                process_incident(inc)
        except Exception as e:
            print("[runner] loop error:", e)
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
