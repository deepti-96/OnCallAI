"""Live alert sources: CloudWatch alarms via SNS -> SQS, and Datadog monitor webhooks.

Each source does two things:
  1. turns the platform's alert into an OnCallAI incident (through the existing
     CloudWatch normalizer, dedupe and enrichment in app/middleware/alert_ingest.py)
  2. pulls the real log lines around the alert time from the same platform and
     writes them where the existing collector already reads logs
"""
