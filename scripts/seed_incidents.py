# scripts/seed_incidents.py
import os, json, datetime
from sqlalchemy import create_engine, text

DB_URL = os.environ.get("DB_URL", "sqlite:///dev.db")
engine = create_engine(DB_URL, future=True)

def iso_utc():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def seed_one():
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO incidents(status, service, environment, severity, payload_json, created_at)
                VALUES(:status, :service, :env, :sev, :payload, :created_at)
            """),
            {
                "status": "OPEN",
                "service": "payment-service",
                "env": "prod",
                "sev": "CRITICAL",
                "payload": json.dumps({
                    "alert": "2025-09-27-seed",
                    "details": "synthetic cloudwatch-like alert",
                    "service": "payment-service"
                }),
                "created_at": iso_utc(),
            }
        )

if __name__ == "__main__":
    seed_one()
    print("Seeded one incident.")
