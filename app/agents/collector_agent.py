from app.config import LOGS_LOCAL_ROOT
from app.db.dal import record_step
from app.middleware.log_collection import build_log_collection_profile, collect_logs_for_incident

def collector_run(incident):
    record_step(incident['id'], 'collector', 'start', 'Collector started')
    profile = build_log_collection_profile(incident)
    record_step(
        incident['id'],
        'collector',
        'select',
        f"Selected {profile['folder']} logs for {profile['service']}",
        {'profile': profile},
        status="OK",
    )
    collection = collect_logs_for_incident(incident, root=LOGS_LOCAL_ROOT)
    record_step(
        incident['id'],
        'collector',
        'retrieve',
        f"Fetched {len(collection['selected_files'])} ranked log files",
        {'files': collection['selected_files'], 'profile': profile},
        status="OK",
    )
    record_step(
        incident['id'],
        'collector',
        'done',
        f"Collected {len(collection['logs'])} supporting log snippets",
        {'selected_files': collection['selected_files']},
        status="OK",
    )
    return collection
