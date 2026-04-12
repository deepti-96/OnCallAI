import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.middleware.alert_ingest import ingest_cloudwatch_alert_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a CloudWatch-style alert JSON file into OnCallAI.")
    parser.add_argument("path", help="Path to the alert JSON file")
    args = parser.parse_args()

    incident_id = ingest_cloudwatch_alert_file(args.path)
    print(f"Ingested alert as incident {incident_id}")


if __name__ == "__main__":
    main()
