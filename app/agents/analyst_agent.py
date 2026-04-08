import re, json
from app.db.dal import record_step

# Tiny rule-based analyst for demo. Replace with RAG+LLM in real use.
RULES = [
    {'pattern': r'connection refused|ECONNREFUSED', 'issue':'Database connection errors', 'root':'DB pod not ready/crashed', 'fix':['Restart DB pod','Increase memory','Check readiness probes']},
    {'pattern': r'OOMKilled|OutOfMemoryError', 'issue':'Service OOM', 'root':'Memory pressure or leak', 'fix':['Increase container memory limit','Investigate leak','Scale horizontally']},
    {'pattern': r'HTTP 500|NullPointerException', 'issue':'HTTP 500 / Null deref', 'root':'Bug introduced in recent deploy', 'fix':['Rollback to last working version','Add null checks','Improve input validation']},
]

def analyze_logs(incident, collected):
    record_step(incident['id'], 'analyst', 'start', 'Analyzing logs with heuristic rules')
    corpus = "\n".join(collected.get('logs', []))[:20000]
    evidence = []
    for rule in RULES:
        if re.search(rule['pattern'], corpus, flags=re.I):
            evidence.append(f"Matched pattern: {rule['pattern']}")
            record_step(incident['id'], 'analyst', 'analyze', f"Pattern match: {rule['pattern']}")
            return {
                'issue': rule['issue'],
                'root_cause': rule['root'],
                'mitigations': rule['fix'],
                'evidence': evidence
            }
    record_step(incident['id'], 'analyst', 'analyze', 'No strong match; recommend human review')
    return {
        'issue': 'Unknown',
        'root_cause': 'Inconclusive',
        'mitigations': ['Escalate to on-call', 'Gather more logs', 'Increase verbosity'],
        'evidence': ['No rule matched']
    }
