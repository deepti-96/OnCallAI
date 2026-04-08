import time

from app.db.dal import init_db, record_incident

# Incidents to insert
incidents = [
    {
        "status": "OPEN",
        "service": "user-service",
        "environment": "production",
        "severity": "CRITICAL",
        "payload": {"source": "jwt-validation", "spike_percentage": 50},
        "created_at": "2025-09-27T20:30:25Z"
    },
    {
        "status": "OPEN",
        "service": "payment-gateway",
        "environment": "production",
        "severity": "CRITICAL",
        "payload": {"source": "ssl-certificate", "spike_percentage": 100},
        "created_at": "2025-09-27T15:45:00Z"
    },
    {
        "status": "OPEN",
        "service": "fraud-service",
        "environment": "production",
        "severity": "HIGH",
        "payload": {"source": "fraud-detection", "spike_percentage": 40},
        "created_at": "2025-09-27T14:30:25Z"
    }
]

if __name__ == "__main__":
    init_db()
    for inc in incidents:
        incident_id = record_incident(
            status=inc["status"],
            service=inc["service"],
            environment=inc["environment"],
            severity=inc["severity"],
            payload=inc["payload"],
            created_at=inc["created_at"]
        )
        print(f"✅ Inserted incident with id={incident_id}")
        time.sleep(30)  # wait 30 seconds before next insert
