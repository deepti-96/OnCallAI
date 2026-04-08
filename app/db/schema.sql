PRAGMA foreign_keys = ON;

-- every agent step (timeline row)
CREATE TABLE IF NOT EXISTS agent_steps (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL,
  agent       TEXT    NOT NULL,     -- collector | analyst | supervisor
  phase       TEXT    NOT NULL,     -- start | retrieve | analyze | summarize | done | error
  message     TEXT    NOT NULL,     -- short human-readable message
  data_json   TEXT    NOT NULL,     -- JSON payload (details)
  ts          TEXT    NOT NULL,     -- ISO8601 UTC timestamp
  status      TEXT                 -- STARTED | OK | WARN | ERROR (optional)
);

-- final (or intermediate) report for an incident
CREATE TABLE IF NOT EXISTS reports (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL,
  report_json TEXT    NOT NULL,     -- structured RCA
  report_md   TEXT    NOT NULL,     -- pretty Markdown
  created_at  TEXT    NOT NULL,     -- ISO8601 UTC
  FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
);

-- minimal incidents table (if you don’t have one yet)
CREATE TABLE IF NOT EXISTS incidents(
  id          TEXT PRIMARY KEY,
  status      TEXT NOT NULL,        -- OPEN | IN_PROGRESS | DONE | FAILED
  service     TEXT NOT NULL,
  environment TEXT NOT NULL,
  severity    TEXT NOT NULL,
  payload_json TEXT,
  created_at  TEXT NOT NULL
);

-- indexes for fast UI reads
CREATE INDEX IF NOT EXISTS idx_steps_inc_ts   ON agent_steps(incident_id, ts);
CREATE INDEX IF NOT EXISTS idx_reports_inc_dt ON reports(incident_id, created_at);
