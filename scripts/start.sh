#!/usr/bin/env bash
# Set up .venv (if needed), run the tests, and start OnCallAI. Everything runs inside .venv.
#   bash scripts/start.sh               simulated MIND, replay demo
#   bash scripts/start.sh --skip-tests  start faster
# Real services are switched on by environment variables:
#   MIND_ENABLED=true MIND_API_KEY=mind_...   real MIND
#   CW_SQS_QUEUE_URL=https://sqs...          real CloudWatch alarms (AWS credentials needed)
#   DD_API_KEY=... DD_APP_KEY=...            pull Datadog logs for webhook alerts
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${CONSOLE_PORT:-8787}"

bash scripts/setup_venv.sh
VPY=.venv/bin/python

if [ "${1:-}" != "--skip-tests" ]; then
  echo "Running tests"
  "$VPY" -m unittest discover -s tests 2>&1 | tail -3
fi

ARGS=()
if [ "${MIND_ENABLED:-false}" != "true" ] || [ -z "${MIND_API_KEY:-}" ]; then ARGS+=(--simulate-mind); fi

URL="http://127.0.0.1:$PORT"
( sleep 1.5; command -v open >/dev/null && open "$URL" ) >/dev/null 2>&1 &
echo "Starting OnCallAI on $URL with $($VPY --version) from .venv (Ctrl+C to stop)"
exec "$VPY" -m app.web.server --port "$PORT" "${ARGS[@]}"
