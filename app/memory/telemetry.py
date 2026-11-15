"""Observability for the MIND path.

Two sinks, both already used by OnCallAI:
  1. agent_steps rows (agent='memory') so the incident timeline shows it.
  2. one JSON line per event on stdout, same shape as runner._log_event.
In-process counters make it easy to assert on in tests and print in demos.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

COUNTERS: Counter = Counter()


def emit(event: str, incident_id: str | None = None, **fields: Any) -> None:
    COUNTERS[event] += 1
    record = {"event": event, "incident_id": incident_id, "component": "mind"}
    record.update(fields)
    print(json.dumps(record, sort_keys=True, default=str))


def reset() -> None:
    COUNTERS.clear()
