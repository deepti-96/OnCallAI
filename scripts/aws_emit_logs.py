"""Write synthetic failing logs into the demo CloudWatch log groups.

    python3 scripts/aws_emit_logs.py                       # checkout 504s after payment v2.15.0
    python3 scripts/aws_emit_logs.py --rounds 2 --pause 30 # keep failing for longer

Uses the same lines as the offline replay, stamped with the current time.
Needs boto3 and logs:CreateLogStream + logs:PutLogEvents.
"""
import argparse
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.integrations.replay import scenario  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--pause", type=float, default=20.0)
    args = ap.parse_args()
    try:
        import boto3
    except ImportError:
        sys.exit("pip install boto3 first")
    logs = boto3.client("logs", region_name=os.getenv("AWS_REGION", "us-east-1"))
    stream = f"oncallai-demo-{int(time.time())}"
    _, events_by_group = scenario("pool-exhaustion")
    for group in events_by_group:
        logs.create_log_stream(logGroupName=group, logStreamName=stream)
    for r in range(args.rounds):
        for group, events in events_by_group.items():
            now = int(time.time() * 1000)
            batch = [{"timestamp": now + i, "message": e["message"]} for i, e in enumerate(events)]
            logs.put_log_events(logGroupName=group, logStreamName=stream, logEvents=batch)
            print(f"round {r + 1}: wrote {len(batch)} lines to {group}")
        if r + 1 < args.rounds:
            time.sleep(args.pause)
    print("Alarm checkout-service-error-burst should fire within 1 to 3 minutes.")


if __name__ == "__main__":
    main()
