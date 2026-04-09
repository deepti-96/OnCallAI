import os, glob, json
from app.config import LOGS_MODE, LOGS_LOCAL_ROOT
from app.db.dal import record_step

def choose_log_folder(incident):
    payload = incident.get("payload") or {}
    signal = " ".join(
        str(value)
        for value in (
            incident.get("alert_type"),
            payload.get("alert_type"),
            payload.get("alert"),
            payload.get("source"),
            incident.get("service"),
        )
        if value
    ).lower()

    if any(token in signal for token in ("db", "database", "sql", "postgres", "mysql")):
        return 'db'
    if any(token in signal for token in ("cpu", "oom", "infra", "memory", "node", "host")):
        return 'infra'
    return 'web'

def fetch_logs(folder):
    root = LOGS_LOCAL_ROOT
    path = os.path.join(root, folder)
    logs = []
    for fp in sorted(glob.glob(os.path.join(path, '*.log')))[:5]:
        with open(fp,'r',encoding='utf-8',errors='ignore') as f:
            logs.append(f.read()[:5000])
    return logs

def collector_run(incident):
    record_step(incident['id'], 'collector', 'start', 'Collector started')
    folder = choose_log_folder(incident)
    record_step(incident['id'], 'collector', 'retrieve', f'Selected logs folder: {folder}', {'folder':folder})
    logs = fetch_logs(folder)
    record_step(incident['id'], 'collector', 'done', f'Fetched {len(logs)} log files')
    return {'folder':folder, 'logs':logs}
