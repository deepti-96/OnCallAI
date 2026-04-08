# scripts/seed_incidents.py
import datetime
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.dal import init_db, record_incident

def iso_utc():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

def seed_one():
    init_db()
    return record_incident(
        status="OPEN",
        service="payment-service",
        environment="prod",
        severity="CRITICAL",
        payload={
            "alert": "2025-09-27-seed",
            "details": "synthetic cloudwatch-like alert",
            "service": "payment-service",
        },
        created_at=iso_utc(),
    )

if __name__ == "__main__":
    incident_id = seed_one()
    print(f"Seeded one incident: {incident_id}")
