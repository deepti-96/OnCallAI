import re

from app.db.dal import record_step
from app.rag.loader import retrieve_examples

# Tiny rule-based analyst for demo. Replace with RAG+LLM in real use.
RULES = [
    {'pattern': r'connection refused|ECONNREFUSED', 'issue':'Database connection errors', 'root':'DB pod not ready/crashed', 'fix':['Restart DB pod','Increase memory','Check readiness probes']},
    {'pattern': r'OOMKilled|OutOfMemoryError', 'issue':'Service OOM', 'root':'Memory pressure or leak', 'fix':['Increase container memory limit','Investigate leak','Scale horizontally']},
    {'pattern': r'HTTP 500|NullPointerException', 'issue':'HTTP 500 / Null deref', 'root':'Bug introduced in recent deploy', 'fix':['Rollback to last working version','Add null checks','Improve input validation']},
]


def _incident_context(incident, collected) -> str:
    payload = incident.get("payload") or {}
    incident_fields = [
        incident.get("service", ""),
        incident.get("environment", ""),
        incident.get("severity", ""),
        payload.get("alert", ""),
        payload.get("details", ""),
        payload.get("source", ""),
        payload.get("alert_type", ""),
    ]
    logs = collected.get("logs", [])
    return "\n".join(str(value) for value in incident_fields + logs if value)[:20000]


def analyze_logs(incident, collected):
    record_step(incident['id'], 'analyst', 'start', 'Analyzing logs with heuristic rules and retrieved examples')
    corpus = _incident_context(incident, collected)
    evidence = []
    retrieved_examples = retrieve_examples(corpus)

    if retrieved_examples:
        evidence.extend(
            f"Retrieved example: {example['root_cause']} (matches={example['match_count']})"
            for example in retrieved_examples
        )
        record_step(
            incident['id'],
            'analyst',
            'retrieve',
            f"Retrieved {len(retrieved_examples)} supporting examples",
            {"examples": retrieved_examples},
            status="OK",
        )

    for rule in RULES:
        if re.search(rule['pattern'], corpus, flags=re.I):
            evidence.append(f"Matched pattern: {rule['pattern']}")
            record_step(incident['id'], 'analyst', 'analyze', f"Pattern match: {rule['pattern']}")
            mitigations = list(rule['fix'])
            if retrieved_examples:
                for example in retrieved_examples:
                    for mitigation in example.get("mitigation", []):
                        if mitigation not in mitigations:
                            mitigations.append(mitigation)
            return {
                'issue': rule['issue'],
                'root_cause': rule['root'],
                'mitigations': mitigations,
                'evidence': evidence,
                'confidence': round(min(0.95, 0.65 + (0.1 * len(retrieved_examples))), 2),
                'retrieved_examples': retrieved_examples,
            }

    if retrieved_examples:
        best_example = retrieved_examples[0]
        record_step(
            incident['id'],
            'analyst',
            'analyze',
            f"Used retrieved context from pattern: {best_example['pattern']}",
            status="WARN",
        )
        return {
            'issue': incident.get('service', 'Unknown service') + ' incident',
            'root_cause': best_example.get('root_cause', 'Inconclusive'),
            'mitigations': best_example.get('mitigation', ['Escalate to on-call']),
            'evidence': evidence,
            'confidence': 0.55,
            'retrieved_examples': retrieved_examples,
        }

    record_step(incident['id'], 'analyst', 'analyze', 'No strong match; recommend human review', status="WARN")
    return {
        'issue': 'Unknown',
        'root_cause': 'Inconclusive',
        'mitigations': ['Escalate to on-call', 'Gather more logs', 'Increase verbosity'],
        'evidence': ['No rule matched'],
        'confidence': 0.3,
        'retrieved_examples': [],
    }
