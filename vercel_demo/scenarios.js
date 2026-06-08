export const SCENARIOS = {
  database: {
    key: "database",
    title: "Payment-service latency alert",
    service: "payment-service",
    ownerTeam: "payments-oncall",
    alarmName: "payment-service-critical-latency",
    source: "CloudWatch",
    severity: "Critical",
    severityClass: "critical",
    occurrenceCount: 4,
    priority: "Immediate",
    alertState: "ALARM",
    summary:
      "Latency alarms are firing repeatedly for a tier-1 payment dependency during checkout traffic spikes.",
    confidence: 0.86,
    headline: "Page payments-oncall and validate database readiness.",
    issue: "Database connection errors",
    rootCause: "DB pod not ready or crashed after elevated load.",
    action: "Page payments-oncall and validate DB readiness before rollback.",
    runbookUrl: "https://example.com/runbooks/payment-latency",
    dashboardUrl: "https://example.com/dashboards/payment-service",
    evidence: [
      "Matched log signals such as ECONNREFUSED from the payment path.",
      "Retrieved similar prior incident patterns from the bundled incident corpus.",
      "Detected repeated alerts and tier-1 service ownership.",
    ],
    nextSteps: [
      "Open the payment-service runbook and verify DB readiness probes.",
      "Inspect recent deployment changes touching the payment-service dependency path.",
      "Scale or restart the affected database pod if readiness remains unstable.",
    ],
    steps: [
      {
        label: "Alert ingested",
        detail: "CloudWatch latency alert normalized into the incident schema with critical severity.",
      },
      {
        label: "Repeated alarms deduplicated",
        detail: "Multiple matching alarms collapsed into one incident with occurrence tracking.",
      },
      {
        label: "Context collected",
        detail: "Service ownership, runbook metadata, and database logs were attached to the incident.",
      },
      {
        label: "Evidence analyzed",
        detail: "Heuristic rules plus retrieved examples identified a likely database connectivity failure.",
      },
      {
        label: "Escalation recommended",
        detail: "Because this is critical, repeated, and tier-1, the system recommends paging payments-oncall.",
      },
    ],
  },
  memory: {
    key: "memory",
    title: "Inventory-service memory pressure",
    service: "inventory-service",
    ownerTeam: "inventory-oncall",
    alarmName: "inventory-service-memory-pressure",
    source: "CloudWatch",
    severity: "High",
    severityClass: "priority",
    occurrenceCount: 2,
    priority: "High",
    alertState: "ALARM",
    summary:
      "The inventory-service is showing repeated memory-related failures during a warehouse sync job window.",
    confidence: 0.78,
    headline: "Notify inventory-oncall and inspect recent memory growth.",
    issue: "Service OOM",
    rootCause: "Container memory pressure or a likely leak in the sync path.",
    action: "Notify inventory-oncall, inspect pod restarts, and increase memory if needed.",
    runbookUrl: "https://example.com/runbooks/inventory-memory",
    dashboardUrl: "https://example.com/dashboards/inventory-service",
    evidence: [
      "Matched OOMKilled and memory pressure signals in infra logs.",
      "Incident age and service tier push the workflow into a high-priority state.",
      "Recent deploy hint suggests reviewing warehouse feed processing changes.",
    ],
    nextSteps: [
      "Check pod restart counts and memory graphs for the inventory-service.",
      "Review the warehouse sync job introduced in the most recent deployment window.",
      "Temporarily scale or increase container memory while a root cause fix is prepared.",
    ],
    steps: [
      {
        label: "Alert ingested",
        detail: "A high-severity memory alarm arrived from CloudWatch for inventory-service.",
      },
      {
        label: "Context collected",
        detail: "The app linked service ownership, escalation policy, and infra log slices.",
      },
      {
        label: "Pattern matched",
        detail: "OOMKilled-related evidence aligned with previous inventory-service incidents.",
      },
      {
        label: "Operator guidance prepared",
        detail: "The app assembled recommended mitigation and escalation options for first responders.",
      },
    ],
  },
  deploy: {
    key: "deploy",
    title: "Checkout-service bad deploy",
    service: "checkout-service",
    ownerTeam: "checkout-oncall",
    alarmName: "checkout-service-http-500-burn",
    source: "CloudWatch",
    severity: "Critical",
    severityClass: "critical",
    occurrenceCount: 3,
    priority: "Immediate",
    alertState: "ALARM",
    summary:
      "Checkout is returning elevated HTTP 500s shortly after a release, creating a high-friction customer path.",
    confidence: 0.82,
    headline: "Page checkout-oncall and evaluate rollback immediately.",
    issue: "HTTP 500 / Null deref",
    rootCause: "A recent deploy likely introduced a null dereference in the checkout request path.",
    action: "Page checkout-oncall, confirm release timing, and rollback if the error budget is burning.",
    runbookUrl: "https://example.com/runbooks/checkout-errors",
    dashboardUrl: "https://example.com/dashboards/checkout-service",
    evidence: [
      "Matched HTTP 500 and NullPointerException-style patterns from application logs.",
      "Service context indicates a tier-1 revenue path with checkout ownership metadata.",
      "The latest deploy hint aligns with changes across cart and payment dependencies.",
    ],
    nextSteps: [
      "Compare the incident start time with the latest checkout deployment.",
      "Use the dashboard link to inspect request spikes and failure-rate trends.",
      "Prepare rollback and communicate impact to the commerce stakeholders if needed.",
    ],
    steps: [
      {
        label: "Alert ingested",
        detail: "Checkout failure-rate alarms entered the incident queue as a critical tier-1 event.",
      },
      {
        label: "Logs retrieved",
        detail: "The collector associated web logs and service ownership metadata with the incident.",
      },
      {
        label: "Likely deploy regression detected",
        detail: "Rule-based analysis linked null dereference signals to the latest release window.",
      },
      {
        label: "Escalation generated",
        detail: "The app recommended paging checkout-oncall and considering rollback before customer impact worsens.",
      },
    ],
  },
  recovery: {
    key: "recovery",
    title: "Billing-service recovered alert",
    service: "billing-service",
    ownerTeam: "billing-platform",
    alarmName: "billing-service-error-rate-recovered",
    source: "CloudWatch",
    severity: "Medium",
    severityClass: "priority",
    occurrenceCount: 1,
    priority: "Monitor",
    alertState: "OK",
    summary:
      "A previously noisy billing alarm has recovered, and the system can close the loop without creating duplicate incidents.",
    confidence: 0.6,
    headline: "Log recovery, notify the owner, and keep monitoring.",
    issue: "Recovered CloudWatch alert",
    rootCause: "The prior error condition cleared before a new escalation was needed.",
    action: "Notify billing-platform, document the recovery, and continue monitoring for recurrence.",
    runbookUrl: "https://example.com/runbooks/billing-recovery",
    dashboardUrl: "https://example.com/dashboards/billing-service",
    evidence: [
      "An OK-state CloudWatch event was linked to the existing incident rather than opening a new one.",
      "Deduplication logic preserved the original timeline and marked the recovery explicitly.",
      "No new high-confidence RCA was required because the alert self-resolved quickly.",
    ],
    nextSteps: [
      "Mark the incident as resolved and keep the report for future retrieval context.",
      "Review whether the original trigger needs a threshold adjustment to reduce noise.",
      "Monitor the next alert cycle to confirm the recovery is stable.",
    ],
    steps: [
      {
        label: "Recovery alert ingested",
        detail: "The OK-state alarm updated the existing billing incident instead of creating a duplicate row.",
      },
      {
        label: "Incident reconciled",
        detail: "Occurrence history and last-seen metadata were updated to reflect the recovery event.",
      },
      {
        label: "Operator view refreshed",
        detail: "The UI now shows the incident as recovered with low urgency escalation guidance.",
      },
    ],
  },
};

export function getScenario(key) {
  return SCENARIOS[key] || SCENARIOS.database;
}
