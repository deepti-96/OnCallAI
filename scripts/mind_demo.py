"""MIND incident-memory demo + the graph-vs-similarity experiment.

    .venv/bin/python scripts/mind_demo.py                 # offline, simulated MIND (FakeMind)
    .venv/bin/python scripts/mind_demo.py --live          # real MIND, needs MIND_API_KEY
    .venv/bin/python scripts/mind_demo.py --live --cleanup  # delete the demo entries from MIND

Uses a throwaway SQLite file, never dev.db. All incidents are synthetic.
"""
import argparse
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import dal  # noqa: E402

dal.DB_FILE = str(pathlib.Path(tempfile.mkdtemp()) / "mind_demo.db")
dal.init_db()

from app.agents.analyst_agent import _incident_context, analyze_logs  # noqa: E402
from app.agents.supervisor import compile_report  # noqa: E402
from app.memory import incident_memory as mem, telemetry  # noqa: E402
from app.memory.demo_data import INCIDENT_A, INCIDENT_B, INCIDENT_C, INCIDENT_D  # noqa: E402
from app.memory.entities import extract_entities  # noqa: E402
from app.memory.fake_mind import FakeMind  # noqa: E402
from app.memory.mind_client import MindClient, MindError  # noqa: E402
from app.rag.loader import retrieve_examples  # noqa: E402

ENTRY_LOG = ROOT / ".local" / "mind_demo_entries.json"

# Phrases unique to each history incident, so we can tell what a retrieval returned
# even when a graph mode returns entity summaries instead of raw entry text.
MARKERS = {
    "A (payment config, the real ancestor)": ["CARD_GATEWAY_TIMEOUT_MS", "v2.14.0", mem.memory_key("demo-inc-A")],
    "C (checkout cascade via payment)": ["circuit breaker", mem.memory_key("demo-inc-C")],
    "D (inventory lookalike)": ["inventory-sync", "memory leak", mem.memory_key("demo-inc-D")],
}


def banner(text):
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78)


def found_in(text):
    low = text.lower()
    return [name for name, marks in MARKERS.items() if any(m.lower() in low for m in marks)] or ["nothing"]


def record(sc):
    dal.record_incident(status="OPEN", service=sc["service"], environment=sc["environment"],
                        severity=sc["severity"], payload=sc["payload"], incident_id=sc["id"])
    return dal.get_incident(sc["id"]), {"logs": sc["logs"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the real MIND API (MIND_API_KEY)")
    ap.add_argument("--wait", type=int, default=90, help="live only: seconds to wait for graph extraction")
    ap.add_argument("--cleanup", action="store_true", help="live only: delete demo entries and exit")
    args = ap.parse_args()

    if args.live:
        key = os.getenv("MIND_API_KEY")
        if not key:
            sys.exit("Set MIND_API_KEY first (m-i-n-d.ai -> Settings -> Developer -> API Keys).")
        client = MindClient(key, os.getenv("MIND_BASE_URL", "https://www.m-i-n-d.ai"), timeout=30)
    else:
        client = FakeMind()

    if args.cleanup:
        ids = json.loads(ENTRY_LOG.read_text()) if ENTRY_LOG.exists() else []
        for eid in ids:
            try:
                client.delete_entry(eid)
                print("deleted", eid)
            except MindError as exc:
                print("could not delete", eid, exc)
        ENTRY_LOG.unlink(missing_ok=True)
        return

    os.environ["MIND_ENABLED"] = "true"
    mem.get_client = lambda: client  # route the pipeline to whichever backend we chose
    created = []
    print(f"Backend: {'REAL MIND (' + client.base_url + ')' if args.live else 'FakeMind simulator (not MIND)'}")
    if args.live:
        try:
            print("Graph stats before:", json.dumps(client.graph_info())[:300])
        except MindError as exc:
            sys.exit(f"MIND not reachable: {exc}")

    # 1. Incident A: triage, then resolve and store the human-confirmed RCA ------------
    banner("STEP 1  Incident A on payment-service: triage, resolve, write RCA to MIND")
    inc, collected = record(INCIDENT_A)
    a = analyze_logs(inc, collected)
    print("Analyst root cause (current logs):", a["root_cause"])
    res = mem.resolve_and_remember(INCIDENT_A["id"], **{k: v for k, v in INCIDENT_A["resolution"].items()},
                                   logs=INCIDENT_A["logs"])
    print("Write-back:", res["status"], res.get("memory_key"))
    created.append(res.get("entry_id"))
    print("Write-back again (should dedupe):",
          mem.resolve_and_remember(INCIDENT_A["id"], **INCIDENT_A["resolution"], logs=INCIDENT_A["logs"])["status"])

    # 2. More history: C is connected to A, D only looks similar -----------------------
    banner("STEP 2  Store connected incident C and lookalike incident D")
    for sc, related in [(INCIDENT_C, [mem.memory_key("demo-inc-A")]), (INCIDENT_D, [])]:
        record(sc)
        r = mem.resolve_and_remember(sc["id"], **sc["resolution"], related_incidents=related, logs=sc["logs"])
        print(sc["id"], r["status"], r.get("memory_key"))
        created.append(r.get("entry_id"))
    if args.live:
        ENTRY_LOG.parent.mkdir(exist_ok=True)
        ENTRY_LOG.write_text(json.dumps([c for c in created if c]))
        print(f"Waiting {args.wait}s for MIND graph extraction...")
        time.sleep(args.wait)

    # 3. Incident B through the pipeline ---------------------------------------------
    banner("STEP 3  Incident B on checkout-service (logs never mention payment-service)")
    inc_b, collected_b = record(INCIDENT_B)
    b = analyze_logs(inc_b, collected_b)
    _, md = compile_report(inc_b, b)
    print(md[md.find("**Root Cause**"): md.find("**Suggested")].strip())
    print(md[md.find("**Historical Context"):].strip() or "(no historical section)")

    # 4. The experiment ---------------------------------------------------------------
    banner("STEP 4  Experiment: what does each retrieval path surface for Incident B?")
    corpus = _incident_context(inc_b, collected_b)
    ents = extract_entities(inc_b, collected_b)
    rows = [("Existing OnCallAI loader (token overlap on examples.jsonl)",
             [f"example: {e['root_cause']}" for e in retrieve_examples(corpus)] or ["nothing"])]
    probes = [
        ("MIND naive  (text similarity), query = B's symptoms+logs", "naive", corpus),
        ("MIND local  (entity walk),     query = just the service", "local",
         f"Find past incidents involving {ents['service']} and the services it depends on."),
        ("MIND hybrid (local+global, no raw text), recall query", "hybrid", b["historical_context"]["query"]),
    ]
    probes.append(("MIND mix    (graph + raw text), same recall query", "mix", b["historical_context"]["query"]))
    for label, mode, q in probes:
        try:
            r = client.query(q, mode=mode, retrieve_only=True, max_context_tokens=6000)
            rows.append((label, found_in(r.get("response", "") + " ".join(map(str, r.get("sources") or [])))))
        except MindError as exc:
            rows.append((label, [f"error: {exc}"]))
    for label, hits in rows:
        print(f"\n{label}\n    -> " + "\n    -> ".join(hits))

    # 5. Resolve B with its real (different) cause, linked to its relatives -------------
    banner("STEP 5  Resolve B with its actual root cause and write it back")
    r = mem.resolve_and_remember(INCIDENT_B["id"], **INCIDENT_B["true_resolution"],
                                 related_incidents=[mem.memory_key("demo-inc-C"), mem.memory_key("demo-inc-A")],
                                 logs=INCIDENT_B["logs"])
    print("B write-back:", r["status"], r.get("memory_key"))
    created.append(r.get("entry_id"))
    if args.live:
        ENTRY_LOG.write_text(json.dumps([c for c in created if c]))
        print(f"Entry ids saved to {ENTRY_LOG}. Remove them later with --live --cleanup.")

    banner("Telemetry counters")
    for k, v in sorted(telemetry.COUNTERS.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
