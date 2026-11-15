#!/usr/bin/env bash
# One command to set up and run OnCallAI locally.
#   ./scripts/start.sh               simulated MIND, replay demo
#   ./scripts/start.sh --skip-tests  start faster
# Real services are switched on by environment variables:
#   MIND_ENABLED=true MIND_API_KEY=mind_...   real MIND
#   CW_SQS_QUEUE_URL=https://sqs...          real CloudWatch alarms (AWS credentials needed)
#   DD_API_KEY=... DD_APP_KEY=...            pull Datadog logs for webhook alerts
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${CONSOLE_PORT:-8787}"

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11 or newer is required. On macOS: brew install python@3.12"; exit 1; }

if [ ! -x .venv-oncallai/bin/python ]; then
  echo "Creating .venv-oncallai with $($PY --version)"
  "$PY" -m venv .venv-oncallai
fi
VPY=.venv-oncallai/bin/python
"$VPY" -m pip install -q --disable-pip-version-check python-dotenv boto3 2>/dev/null \
  || echo "Could not install python-dotenv/boto3 (offline?). The replay demo still works."

if [ "${1:-}" != "--skip-tests" ]; then
  echo "Running tests"
  "$VPY" -m unittest discover -s tests 2>&1 | tail -3
fi

ARGS=()
if [ "${MIND_ENABLED:-false}" != "true" ] || [ -z "${MIND_API_KEY:-}" ]; then ARGS+=(--simulate-mind); fi

URL="http://127.0.0.1:$PORT"
( sleep 1.5; command -v open >/dev/null && open "$URL" ) >/dev/null 2>&1 &
echo "Starting OnCallAI on $URL (Ctrl+C to stop)"
exec "$VPY" -m app.web.server --port "$PORT" "${ARGS[@]}"
