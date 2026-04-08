# app/runner.py
import os, time, traceback
from app.db.dal import (
    init_db, get_open_incidents, mark_in_progress, mark_done, mark_failed,
    record_step, save_report
)

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

def process_incident(inc: dict):
    iid = inc["id"]
    try:
        mark_in_progress(iid)
        record_step(iid, "collector", "start", "Starting collection", status="STARTED")

        # TODO: your real collection here
        # e.g., choose folders, fetch logs...
        record_step(iid, "collector", "retrieve", "Selected folders & fetched logs", status="OK")

        # TODO: your real analysis here (RAG/LLM)
        rca = {
            "issue": "Demo issue",
            "root_cause": "Demo root cause",
            "mitigations": [{"action": "Demo mitigation"}],
            "confidence": 0.9,
        }
        record_step(iid, "analyst", "summarize", "Drafted RCA", {"issue": rca["issue"]}, status="OK")

        report_md = f"""# Incident {iid} — RCA

**Issue:** {rca['issue']}
**Root cause:** {rca['root_cause']}
**Confidence:** {rca['confidence']}

## Suggested mitigations
- {rca['mitigations'][0]['action']}
"""
        save_report(iid, rca, report_md)

        record_step(iid, "supervisor", "done", "Incident processed", status="OK")
        mark_done(iid)
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
