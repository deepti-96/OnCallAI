import datetime
import pathlib
import sys
from typing import Any, Dict

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.middleware.alert_ingest import ingest_cloudwatch_alert


def sample_cloudwatch_alarm(
    service: str = "payment-service",
    environment: str = "prod",
    severity: str = "CRITICAL",
    state: str = "ALARM",
) -> Dict[str, Any]:
    return {
        "AlarmName": f"{service}-{severity.lower()}-latency",
        "AlarmArn": f"arn:aws:cloudwatch:us-east-1:123456789012:alarm:{service}-{severity.lower()}-latency",
        "NewStateValue": state,
        "NewStateReason": f"{severity.title()} latency threshold breached for {service}",
        "StateChangeTime": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Region": "us-east-1",
        "Trigger": {
            "MetricName": "Duration",
            "Namespace": "AWS/Lambda",
            "Dimensions": [
                {"name": "service", "value": service},
                {"name": "environment", "value": environment},
            ],
        },
        "OnCallAI": {
            "service": service,
            "environment": environment,
            "severity": severity,
        },
    }


def simulate_cloudwatch_alarm(**kwargs: Any) -> str:
    return ingest_cloudwatch_alert(sample_cloudwatch_alarm(**kwargs))


if __name__ == "__main__":
    incident_id = simulate_cloudwatch_alarm()
    print(f"Simulated CloudWatch alert created incident {incident_id}")
