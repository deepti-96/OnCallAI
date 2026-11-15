"""OnCallAI local console.

    bash scripts/start.sh                         # sets up .venv, runs tests, starts this
    .venv/bin/python -m app.web.server --simulate-mind   # start only
    open http://localhost:8787

Live sources (both optional, both feed the same pipeline):
  * CloudWatch alarm -> SNS -> SQS: set CW_SQS_QUEUE_URL and AWS credentials.
    A background thread long-polls the queue and pulls CloudWatch Logs per alarm.
  * Datadog monitor webhook: POST /api/webhooks/datadog. Set DD_API_KEY and
    DD_APP_KEY to also pull Datadog logs. Optional DATADOG_WEBHOOK_TOKEN.

Real MIND: MIND_ENABLED=true MIND_API_KEY=mind_xxx. Otherwise --simulate-mind.

Routes:
  GET  /                              product page
  GET  /console                       console
  GET  /api/state                     sources, fetched logs, incidents, MIND status
  GET  /api/incidents/<id>            incident, timeline, report
  POST /api/incidents/<id>/resolve    confirm RCA, write to MIND
  POST /api/webhooks/datadog          Datadog webhook receiver
  POST /api/demo/replay               replay a recorded SNS->SQS alarm through the real SQS code path
  POST /api/demo/history              store synthetic past incidents A, C, D in MIND
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import pathlib
import re
import sqlite3
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WEB = pathlib.Path(__file__).parent
PAGES = {"/": WEB / "landing.html", "/index.html": WEB / "landing.html", "/console": WEB / "console.html"}
STATIC = (WEB / "static").resolve()
TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2",
         ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}

STATE: Dict[str, Any] = {"mind_mode": "off", "worker_errors": 0, "logs_root": ".local/live_logs"}


def build_app(db_file: str, logs_root: str, simulate_mind: bool):
    from app.db import dal
    pathlib.Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    dal.DB_FILE = db_file
    dal.init_db()
    STATE["logs_root"] = logs_root
    pathlib.Path(logs_root).mkdir(parents=True, exist_ok=True)

    from app.agents import collector_agent
    collector_agent.LOGS_LOCAL_ROOT = logs_root  # the existing collector reads fetched logs from here

    from app.memory import config as mind_config, incident_memory as mem
    from app.memory.fake_mind import FakeMind
    if mind_config.mind_enabled():
        STATE["mind_mode"] = "live"
        STATE["mind_base_url"] = mind_config.MIND_BASE_URL
    elif simulate_mind:
        fake = FakeMind()
        mem.get_client = lambda: fake
        STATE["mind_mode"] = "simulated"
        STATE["fake"] = fake
    STATE["mind_query_mode"] = mind_config.MIND_QUERY_MODE

    from app.integrations import cloudwatch_sqs
    try:
        STATE["cloudwatch"] = cloudwatch_sqs.from_env(logs_root)
    except Exception as exc:  # missing boto3 or credentials should not stop the console
        STATE["cloudwatch"] = None
        STATE["cloudwatch_error"] = f"{type(exc).__name__}: {exc}"
    STATE["datadog_logs"] = bool(os.getenv("DD_API_KEY") and os.getenv("DD_APP_KEY"))


def worker_loop(stop: threading.Event):
    from app.db import dal
    import app.runner as runner
    while not stop.is_set():
        try:
            inc = dal.claim_next_queued_incident()
            if inc is None:
                stop.wait(0.7)
                continue
            runner.process_incident(inc)
        except Exception:
            STATE["worker_errors"] += 1
            traceback.print_exc()
            stop.wait(1)


def sqs_loop(stop: threading.Event):
    src = STATE.get("cloudwatch")
    while src and not stop.is_set():
        try:
            src.poll_once(wait_seconds=10)
        except Exception as exc:  # network or auth error: back off and keep going
            src.stats["errors"] += 1
            src.stats["last_error"] = f"{type(exc).__name__}: {exc}"
            stop.wait(5)


def _ledger_rows():
    from app.db import dal
    try:
        con = sqlite3.connect(dal.DB_FILE)
        try:
            rows = con.execute("SELECT incident_id, memory_key, status, written_at FROM mind_memory_writes").fetchall()
        finally:
            con.close()
    except sqlite3.OperationalError:
        return {}
    return {r[0]: {"memory_key": r[1], "status": r[2], "written_at": r[3]} for r in rows}


def api_state() -> Dict[str, Any]:
    from app.db import dal
    from app.integrations.common import recent_lines
    from app.memory import telemetry
    ledger = _ledger_rows()
    incidents = []
    for inc in dal.list_incidents(60):
        rep = dal.get_latest_report(inc["id"])
        hist = ((rep or {}).get("report") or {}).get("historical_context") or {}
        p = inc.get("payload") or {}
        incidents.append({
            "id": inc["id"], "service": inc["service"], "environment": inc["environment"],
            "severity": inc["severity"], "status": inc["status"], "workflow_status": inc.get("workflow_status"),
            "resolution_status": inc.get("resolution_status"), "source": inc.get("source"),
            "created_at": inc.get("created_at"), "occurrence_count": inc.get("occurrence_count"),
            "alert": p.get("alert") or p.get("alarm_name") or "", "reason": p.get("reason") or "",
            "mind_status": hist.get("status"), "mind_used": hist.get("used_in_rca"),
            "mind_history": hist.get("historical_incidents"), "memory": ledger.get(inc["id"]),
        })
    cw = STATE.get("cloudwatch")
    mind = {"mode": STATE["mind_mode"], "query_mode": STATE.get("mind_query_mode"), "base_url": STATE.get("mind_base_url")}
    if STATE.get("fake"):
        mind["entries"] = len(STATE["fake"].entries)
    return {
        "mind": mind,
        "sources": {
            "cloudwatch": {"enabled": bool(cw), "queue_url": cw.queue_url if cw else None,
                           "stats": cw.stats if cw else None, "error": STATE.get("cloudwatch_error")},
            "datadog": {"endpoint": "/api/webhooks/datadog", "logs_api": STATE["datadog_logs"],
                        "token_required": bool(os.getenv("DATADOG_WEBHOOK_TOKEN"))},
        },
        "telemetry": dict(telemetry.COUNTERS),
        "logs": recent_lines(80),
        "incidents": incidents,
        "worker_errors": STATE["worker_errors"],
    }


def api_incident(incident_id: str):
    from app.db import dal
    inc = dal.get_incident(incident_id)
    if not inc:
        return None
    return {"incident": inc, "steps": dal.list_steps(incident_id), "report": dal.get_latest_report(incident_id),
            "memory": _ledger_rows().get(incident_id)}


def seed_history():
    from app.db import dal
    from app.memory import incident_memory as mem
    from app.memory.demo_data import HISTORY
    out = []
    for sc in HISTORY:
        if dal.get_incident(sc["id"]) is None:
            dal.record_incident(status="OPEN", service=sc["service"], environment=sc["environment"],
                                severity=sc["severity"], payload=dict(sc["payload"], source="history-seed"),
                                incident_id=sc["id"])
        related = [mem.memory_key("demo-inc-A")] if sc["id"] == "demo-inc-C" else []
        r = mem.resolve_and_remember(sc["id"], **sc["resolution"], related_incidents=related, logs=sc["logs"])
        out.append({"id": sc["id"], "status": r["status"], "memory_key": r.get("memory_key")})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "OnCallAI-Console/1.0"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, obj: Any):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Any:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, path: pathlib.Path, ctype: str, cache: bool = False):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in PAGES:
            self._file(PAGES[path], "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            target = (STATIC / path[len("/static/"):]).resolve()
            if STATIC not in target.parents or not target.is_file() or target.suffix not in TYPES:
                return self._json(404, {"error": "not found"})
            self._file(target, TYPES[target.suffix], cache=target.suffix == ".woff2")
        elif self.path == "/api/state":
            self._json(200, api_state())
        elif m := re.fullmatch(r"/api/incidents/([\w.-]+)", self.path):
            data = api_incident(m.group(1))
            self._json(200 if data else 404, data or {"error": "not found"})
        elif self.path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            if self.path == "/api/webhooks/datadog":
                token = os.getenv("DATADOG_WEBHOOK_TOKEN")
                if token and not hmac.compare_digest(self.headers.get("X-OnCallAI-Token", ""), token):
                    return self._json(401, {"error": "bad token"})
                from app.integrations.datadog import handle_webhook
                return self._json(200, handle_webhook(self._body(), STATE["logs_root"]))
            if m := re.fullmatch(r"/api/incidents/([\w.-]+)/resolve", self.path):
                from app.memory.incident_memory import resolve_and_remember
                body = self._body()
                if not str(body.get("root_cause", "")).strip():
                    return self._json(400, {"error": "root_cause is required"})
                result = resolve_and_remember(
                    m.group(1), body["root_cause"].strip(),
                    [x.strip() for x in body.get("mitigation", []) if str(x).strip()],
                    affected_component=body.get("affected_component") or None,
                    deployment=body.get("deployment") or None,
                    related_incidents=body.get("related_incidents") or [])
                return self._json(200, {k: v for k, v in result.items() if k != "record"})
            if self.path == "/api/demo/replay":
                from app.integrations.replay import replay
                scenario = self._body().get("scenario", "pool-exhaustion")
                if scenario not in ("pool-exhaustion", "config-timeout", "recovery"):
                    return self._json(400, {"error": "unknown scenario"})
                return self._json(200, {"incidents": replay(scenario, STATE["logs_root"])})
            if self.path == "/api/demo/history":
                return self._json(200, {"seeded": seed_history()})
            self._json(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})


def main():
    ap = argparse.ArgumentParser(description="OnCallAI local console")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.getenv("CONSOLE_PORT", "8787")))
    ap.add_argument("--db", default=os.getenv("CONSOLE_DB", ".local/console.db"))
    ap.add_argument("--logs-root", default=os.getenv("CONSOLE_LOGS_ROOT", ".local/live_logs"))
    ap.add_argument("--simulate-mind", action="store_true", help="use the in-memory MIND simulator")
    args = ap.parse_args()

    os.chdir(ROOT)
    build_app(args.db, args.logs_root, args.simulate_mind)
    stop = threading.Event()
    threading.Thread(target=worker_loop, args=(stop,), daemon=True).start()
    if STATE.get("cloudwatch"):
        threading.Thread(target=sqs_loop, args=(stop,), daemon=True).start()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    cw = STATE.get("cloudwatch")
    print(f"OnCallAI on http://{args.host}:{args.port}   console: http://{args.host}:{args.port}/console")
    print(f"  MIND: {STATE['mind_mode']}")
    print(f"  CloudWatch via SQS: {cw.queue_url if cw else 'off (set CW_SQS_QUEUE_URL)'}")
    print(f"  Datadog webhook: POST http://{args.host}:{args.port}/api/webhooks/datadog")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    main()
