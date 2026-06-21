import { getScenario } from "../../vercel_demo/scenarios.js";
import { buildCloudWatchEvent, buildCloudWatchLogSource } from "./cloudwatch-event.js";

const INGESTION_SOURCE_LABELS = {
  cloudwatch: "CloudWatch",
  pagerduty: "PagerDuty",
  datadog: "Datadog",
  grafana: "Grafana",
};

function titleCase(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1).toLowerCase() : value;
}

function getSeverityClass(severity) {
  return severity.toLowerCase() === "critical" ? "critical" : "priority";
}

export function buildScenarioRun({
  scenario: scenarioKey = "database",
  severity = "auto",
  volume = "auto",
  ingestion_source: ingestionSource = "cloudwatch",
} = {}) {
  const scenario = getScenario(scenarioKey);
  const sourceLabel = INGESTION_SOURCE_LABELS[ingestionSource] || INGESTION_SOURCE_LABELS.cloudwatch;
  const createdAt = new Date().toISOString();
  const resolvedSeverity = severity === "auto" ? scenario.severity : titleCase(severity);
  const occurrenceCount =
    volume === "auto" ? scenario.occurrenceCount : volume === "repeat" ? Math.max(3, scenario.occurrenceCount) : 1;
  const repeatLabel = occurrenceCount > 1 ? `${occurrenceCount} repeated alerts` : "Single alert";
  const processedLabel = occurrenceCount > 1 ? "were" : "was";
  const incidentId = crypto.randomUUID();
  const status = scenario.alertState === "OK" ? "RESOLVED" : "DONE";
  const cloudwatchEvent = buildCloudWatchEvent({
    scenario,
    incident: { created_at: createdAt, alert_state: scenario.alertState },
    occurrenceCount,
    severity: resolvedSeverity,
  });
  const cloudwatchLogs = buildCloudWatchLogSource({ scenario });

  const incident = {
    id: incidentId,
    service: scenario.service,
    title: scenario.title,
    status,
    severity: resolvedSeverity,
    severity_class: getSeverityClass(resolvedSeverity),
    source: sourceLabel,
    alert_state: scenario.alertState,
    occurrence_count: occurrenceCount,
    owner_team: scenario.ownerTeam,
    alarm_name: scenario.alarmName,
    escalation_priority: scenario.priority,
    escalation_target: scenario.ownerTeam,
    runbook_url: scenario.runbookUrl,
    dashboard_url: scenario.dashboardUrl,
    scenario_key: scenario.key,
    summary: scenario.summary,
    created_at: createdAt,
    updated_at: createdAt,
  };

  const steps = scenario.steps.map((step, index) => ({
    id: crypto.randomUUID(),
    incident_id: incidentId,
    phase: `workflow/${index + 1}`,
    description: step.label,
    detail: step.detail,
    status: "completed",
    created_at: new Date(Date.now() + index * 1000).toISOString(),
  }));

  const report = {
    id: crypto.randomUUID(),
    incident_id: incidentId,
    created_at: createdAt,
    report: {
      headline: scenario.headline,
      confidence: scenario.confidence,
      issue: scenario.issue,
      root_cause: scenario.rootCause,
      recommended_action: scenario.action,
      impact: scenario.impact,
      trigger: `${sourceLabel} alert · ${scenario.trigger}`,
      evidence: scenario.evidence,
      next_steps: scenario.nextSteps,
      summary: scenario.summary,
      repeat_label: repeatLabel,
      ingestion_source: ingestionSource,
      cloudwatch_event: cloudwatchEvent,
      cloudwatch_logs: cloudwatchLogs,
      storage_ready_message:
        "When Supabase is connected, this incident is stored durably in Postgres and can be reloaded from the hosted app.",
    },
  };

  const preview = {
    headline: `${resolvedSeverity} ${scenario.title}`,
    status:
      status === "RESOLVED"
        ? "Recovered incident recorded"
        : "Incident stored and ready for operator review",
    summary: `${scenario.summary} ${repeatLabel} ${processedLabel} processed through the live incident workflow.`,
    outcome: scenario.action,
    log: [
      `Created incident ${incidentId} for ${scenario.service}.`,
      `Observed signal from ${sourceLabel}: ${scenario.trigger}`,
      `Normalized ${sourceLabel} payload into the hosted incident schema.`,
      `CloudWatch source: ${scenario.cloudWatchLogGroup} (${scenario.awsRegion})`,
      `Stored alert metadata with ${occurrenceCount} occurrence${occurrenceCount === 1 ? "" : "s"}.`,
      `Attached runbook, dashboard, and owner context for ${scenario.ownerTeam}.`,
      `Generated explainable report with escalation priority ${scenario.priority}.`,
    ],
  };

  return {
    scenario,
    incident,
    steps,
    report,
    preview,
  };
}
