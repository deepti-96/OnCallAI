"""Mark an incident resolved and write the confirmed RCA to MIND.

    python3 scripts/resolve_incident.py --id <incident_id> \
        --root-cause "..." --mitigation "..." --mitigation "..." \
        [--component payment-service] [--deployment "payment-service v2.15.0"]

    python3 scripts/resolve_incident.py --retry-pending   # flush write-backs that failed earlier

Needs MIND_ENABLED=true and MIND_API_KEY, otherwise it only resolves locally.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.dal import init_db  # noqa: E402
from app.memory.incident_memory import resolve_and_remember, retry_pending_writes  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id")
    ap.add_argument("--root-cause")
    ap.add_argument("--mitigation", action="append", default=[])
    ap.add_argument("--component")
    ap.add_argument("--deployment")
    ap.add_argument("--related", action="append", default=[], help="memory key of a related past incident")
    ap.add_argument("--retry-pending", action="store_true")
    args = ap.parse_args()
    init_db()
    if args.retry_pending:
        print(f"retried {retry_pending_writes()} pending write-backs")
        return
    if not (args.id and args.root_cause):
        ap.error("--id and --root-cause are required")
    result = resolve_and_remember(args.id, args.root_cause, args.mitigation, affected_component=args.component,
                                  deployment=args.deployment, related_incidents=args.related)
    print(json.dumps({k: v for k, v in result.items() if k != "record"}, indent=2))


if __name__ == "__main__":
    main()
