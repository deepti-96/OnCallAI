#!/usr/bin/env bash
# Create .venv with Python 3.11+ and install requirements-console.txt into it.
# Safe to run again; it reuses the existing .venv.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11 or newer is required. On macOS: brew install python@3.12"; exit 1; }

if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo ".venv uses Python older than 3.11; recreating it"
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv with $($PY --version)"
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements-console.txt
echo "Ready: $(.venv/bin/python --version) in .venv"
echo "Activate it in this terminal with: source .venv/bin/activate"
