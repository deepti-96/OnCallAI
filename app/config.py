import os

try:
    from dotenv import load_dotenv
except ImportError:  # Optional during lightweight local runs
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
DB_FILE = os.getenv("DB_FILE", "dev.db")
LOGS_LOCAL_ROOT = os.getenv("LOGS_LOCAL_ROOT", "app/logs")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CLOUDWATCH_MAX_RECORDS = int(os.getenv("CLOUDWATCH_MAX_RECORDS", "25"))
