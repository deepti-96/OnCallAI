import { SCENARIOS, getScenario } from "./scenarios.js";

const INGESTION_INTEGRATIONS = {
  cloudwatch: {
    key: "cloudwatch",
    label: "CloudWatch alarm intake",
    detail: "AWS CloudWatch alarms are normalized directly into the hosted incident workflow.",
    submitLabel: "Submitting CloudWatch alarm to the hosted app...",
    sourceLabel: "CloudWatch",
  },
  pagerduty: {
    key: "pagerduty",
    label: "PagerDuty event intake",
    detail: "PagerDuty webhooks can be normalized into the same incident schema and operator workflow.",
    submitLabel: "Submitting PagerDuty event to the hosted app...",
    sourceLabel: "PagerDuty",
  },
  datadog: {
    key: "datadog",
    label: "Datadog monitor intake",
    detail: "Datadog alerts can flow through the same collector, retrieval, triage, and supervisor path.",
    submitLabel: "Submitting Datadog monitor alert to the hosted app...",
    sourceLabel: "Datadog",
  },
  grafana: {
    key: "grafana",
    label: "Grafana alert intake",
    detail: "Grafana-managed alerts can be mapped into the shared incident record and escalation flow.",
    submitLabel: "Submitting Grafana alert to the hosted app...",
    sourceLabel: "Grafana",
  },
};

const THEME_STORAGE_KEY = "oncallai-theme";

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
  }
}

function applyTheme(theme) {
  const resolvedTheme = theme === "dark" ? "dark" : "light";
  document.body.dataset.theme = resolvedTheme;

  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    const darkMode = resolvedTheme === "dark";
    toggle.textContent = darkMode ? "Light mode" : "Dark mode";
    toggle.setAttribute("aria-pressed", String(darkMode));
  }
}

function getStoredTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch (_error) {
    return null;
  }
}

function persistTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch (_error) {
    // Ignore storage failures; theme still applies for the current session.
  }
}

function renderList(id, values) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = values.map((value) => `<li>${value}</li>`).join("");
}

function renderSteps(steps) {
  const el = document.getElementById("scenario-steps");
  if (!el) return;
  el.innerHTML = steps
    .map(
      (step, index) => `
        <article class="step-card">
          <span class="step-marker">${index + 1}</span>
          <div>
            <strong>${step.label}</strong>
            <p>${step.detail}</p>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderSandboxLog(lines) {
  const el = document.getElementById("sandbox-log");
  if (!el) return;
  el.innerHTML = lines
    .map(
      (line, index) =>
        `<div class="sandbox-log-line${index === lines.length - 1 ? " active" : ""}">${line}</div>`,
    )
    .join("");
}

function extendLogWithGraphTrace(lines, graphTrace = []) {
  if (!Array.isArray(graphTrace) || !graphTrace.length) {
    return lines;
  }

  const graphLines = graphTrace.map((entry) => `${entry.node}: ${entry.detail}`);
  return [...lines, ...graphLines];
}

function renderRecentRuns(incidents = []) {
  const el = document.getElementById("recent-runs");
  if (!el) return;

  if (!incidents.length) {
    el.innerHTML = `<div class="recent-run-empty">No runs recorded yet.</div>`;
    return;
  }

  el.innerHTML = incidents
    .map(
      (incident) => `
        <button class="recent-run-card button-reset" data-incident-id="${incident.id}" type="button">
          <div class="recent-run-row">
            <strong>${incident.service}</strong>
            <span class="badge ${String(incident.severity).toLowerCase() === "critical" ? "critical" : "priority"}">${incident.severity}</span>
          </div>
          <p>${incident.title}</p>
          <div class="recent-run-meta">
            <span>${incident.status}</span>
            <span>${incident.occurrence_count || 1} alert${(incident.occurrence_count || 1) === 1 ? "" : "s"}</span>
            <span>${incident.escalation_priority || "Monitor"}</span>
          </div>
        </button>
      `,
    )
    .join("");
}

function renderStorageStatus(storage) {
  if (!storage) return;
  setText("storage-label", storage.label);
  setText("storage-detail", storage.detail);
}

function renderReasoningStatus(reasoning) {
  if (!reasoning) return;
  setText("reasoning-label", reasoning.label);
  setText("reasoning-detail", reasoning.detail);
}

function renderCombinedReasoning(reasoning, retrieval = null) {
  if (!reasoning) return;
  const detail = retrieval ? `${reasoning.detail} ${retrieval.detail}` : reasoning.detail;
  renderReasoningStatus({
    ...reasoning,
    detail,
  });
}

function renderLatestIncident(incident) {
  if (!incident) return;
  setText("latest-incident-id", incident.id);
  setText("latest-incident-meta", `${incident.service} · ${incident.severity} · ${incident.status}`);
  setText("latest-owner-team", incident.owner_team || incident.escalation_target || "Unassigned");
  setText(
    "latest-escalation-meta",
    `${incident.escalation_priority || "Monitor"} priority${incident.alarm_name ? ` · ${incident.alarm_name}` : ""}`,
  );
}

function getSelectedIntegrationKey() {
  return document.querySelector(".integration-button.active")?.dataset.integration || "cloudwatch";
}

function getSelectedIntegration() {
  return INGESTION_INTEGRATIONS[getSelectedIntegrationKey()] || INGESTION_INTEGRATIONS.cloudwatch;
}

function renderIntegrationStatus(integration) {
  setText("integration-label", integration.label);
  setText("integration-detail", integration.detail);
}

function setActiveIntegration(integrationKey) {
  const integration = INGESTION_INTEGRATIONS[integrationKey] || INGESTION_INTEGRATIONS.cloudwatch;

  document.querySelectorAll(".integration-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.integration === integration.key);
  });

  renderIntegrationStatus(integration);
}

function renderScenario(key) {
  const scenario = getScenario(key);
  const integration = getSelectedIntegration();

  document.querySelectorAll(".scenario-chip").forEach((button) => {
    const isActive = button.dataset.scenario === key;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  setText("scenario-title", scenario.title);
  setText("scenario-source", integration.sourceLabel);
  setText("scenario-repeats", `${scenario.occurrenceCount}x`);
  setText("scenario-priority", scenario.priority);
  setText("scenario-alarm-name", scenario.alarmName);
  setText("scenario-region", scenario.awsRegion || "us-east-1");
  setText("scenario-log-group", scenario.cloudWatchLogGroup || "n/a");
  setText("scenario-summary", scenario.summary);
  setText("scenario-severity", scenario.severity);

  const severityBadge = document.getElementById("scenario-severity");
  if (severityBadge) {
    severityBadge.className = `badge ${scenario.severityClass}`;
  }

  setText("output-headline", scenario.headline);
  setText("output-confidence", `Confidence ${scenario.confidence.toFixed(2)}`);
  setText("output-issue", scenario.issue);
  setText("output-root-cause", scenario.rootCause);
  setText("output-action", scenario.action);
  setText("sandbox-trigger", `${integration.sourceLabel} alert · ${scenario.trigger}`);
  setText("sandbox-impact", scenario.impact);
  setText("sandbox-alarm-name", scenario.alarmName);
  setText(
    "sandbox-metric-signal",
    `${scenario.metricNamespace}/${scenario.metricName} > ${scenario.threshold} ${scenario.metricUnit || ""}`.trim(),
  );
  setText(
    "sandbox-log-source",
    `${scenario.cloudWatchLogGroup} · ${scenario.cloudWatchStreamPrefix} · ${scenario.awsRegion || "us-east-1"}`,
  );
  renderList("output-evidence", scenario.evidence);
  renderList("output-next-steps", scenario.nextSteps);
  renderSteps(scenario.steps);
}

function renderIncidentDetail({ incident, steps = [], report = null }) {
  if (!incident) return;
  const cloudwatchEvent = report?.cloudwatch_event || null;
  const cloudwatchLogs = report?.cloudwatch_logs || report?.log_context?.source || null;
  const metric = cloudwatchEvent?.detail?.configuration?.metrics?.[0]?.metricStat?.metric;
  const alarmReason = cloudwatchEvent?.detail?.state?.reason;

  setText("scenario-title", incident.title || incident.service || "Incident");
  setText("scenario-source", incident.source || "Unknown");
  setText("scenario-repeats", `${incident.occurrence_count || 1}x`);
  setText("scenario-priority", incident.escalation_priority || "Monitor");
  setText("scenario-alarm-name", incident.alarm_name || cloudwatchEvent?.detail?.alarmName || "Unknown");
  setText("scenario-region", cloudwatchEvent?.region || cloudwatchLogs?.region || "us-east-1");
  setText("scenario-log-group", cloudwatchLogs?.log_group || "n/a");
  setText("scenario-summary", incident.summary || "Incident context is available for this run.");
  setText("scenario-severity", incident.severity || "Unknown");

  const severityBadge = document.getElementById("scenario-severity");
  if (severityBadge) {
    const severityClass = String(incident.severity || "").toLowerCase() === "critical" ? "critical" : "priority";
    severityBadge.className = `badge ${severityClass}`;
  }

  setText("output-headline", report?.headline || "Incident response available");
  setText("output-confidence", report?.confidence ? `Confidence ${Number(report.confidence).toFixed(2)}` : incident.status);
  setText("output-issue", report?.issue || "Incident details captured");
  setText("output-root-cause", report?.root_cause || "Root cause guidance is not available yet.");
  setText("output-action", report?.recommended_action || "Review the incident and take the next operational step.");
  setText("sandbox-trigger", report?.trigger || incident.alarm_name || "Alert signal details are not available.");
  setText("sandbox-impact", report?.impact || incident.summary || "Operational impact details are not available.");
  setText("sandbox-alarm-name", incident.alarm_name || cloudwatchEvent?.detail?.alarmName || "Unknown");
  setText(
    "sandbox-metric-signal",
    metric
      ? `${metric.namespace}/${metric.name} · ${alarmReason || "Threshold breached"}`
      : "The triggering metric and threshold will appear here.",
  );
  setText(
    "sandbox-log-source",
    cloudwatchLogs
      ? `${cloudwatchLogs.log_group || "n/a"} · ${cloudwatchLogs.stream_prefix || "n/a"} · ${cloudwatchLogs.region || "us-east-1"}`
      : "The CloudWatch log group and stream prefix will appear here.",
  );
  renderList("output-evidence", report?.evidence || ["No additional evidence was stored for this incident."]);
  renderList("output-next-steps", report?.next_steps || ["Review incident ownership and the current service state."]);

  renderSteps(
    steps.map((step) => ({
      label: step.description,
      detail: step.detail || step.phase,
    })),
  );
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || payload.error || `Request failed with ${response.status}`);
  }
  return response.json();
}

function localPreviewForScenario(scenarioKey, severityMode, volumeMode) {
  const scenario = getScenario(scenarioKey);
  const integration = getSelectedIntegration();
  const severityLabel = severityMode === "auto" ? scenario.severity : severityMode[0].toUpperCase() + severityMode.slice(1);
  const occurrenceCount =
    volumeMode === "auto" ? scenario.occurrenceCount : volumeMode === "repeat" ? Math.max(3, scenario.occurrenceCount) : 1;
  const repeatLabel = occurrenceCount === 1 ? "single alert" : `${occurrenceCount} repeated alerts`;
  const incidentId = `local-${scenario.key}-${severityLabel.toLowerCase()}`;
  const incident = {
    id: incidentId,
    title: scenario.title,
    service: scenario.service,
    severity: severityLabel,
    status: scenario.alertState === "OK" ? "RESOLVED" : "DONE",
    source: integration.sourceLabel,
    occurrence_count: occurrenceCount,
    escalation_priority: scenario.priority,
    owner_team: scenario.ownerTeam,
    alarm_name: scenario.alarmName,
    summary: scenario.summary,
  };
  const report = {
    headline: scenario.headline,
    confidence: scenario.confidence,
    issue: scenario.issue,
    root_cause: scenario.rootCause,
    recommended_action: scenario.action,
      trigger: `${integration.sourceLabel} alert · ${scenario.trigger}`,
    impact: scenario.impact,
    evidence: scenario.evidence,
    next_steps: scenario.nextSteps,
    cloudwatch_event: {
      region: scenario.awsRegion || "us-east-1",
      detail: {
        alarmName: scenario.alarmName,
        state: {
          reason: scenario.trigger,
        },
        configuration: {
          metrics: [
            {
              metricStat: {
                metric: {
                  namespace: scenario.metricNamespace,
                  name: scenario.metricName,
                },
              },
            },
          ],
        },
      },
    },
    cloudwatch_logs: {
      log_group: scenario.cloudWatchLogGroup,
      stream_prefix: scenario.cloudWatchStreamPrefix,
      region: scenario.awsRegion || "us-east-1",
    },
  };

  return {
    preview: {
      headline: `${severityLabel} ${scenario.title}`,
      status: "Local sample response",
      summary: `${scenario.summary} This local page is showing a full incident response for ${repeatLabel}.`,
      outcome: scenario.action,
      log: [
        `Created a local sample incident for ${scenario.service}.`,
        `Observed signal from ${integration.sourceLabel}: ${scenario.trigger}`,
        `Applied ${repeatLabel} behavior to the incident record.`,
        `Prepared issue, escalation, and next-action guidance for review.`,
      ],
    },
    incident,
    steps: scenario.steps.map((step) => ({
      description: step.label,
      detail: step.detail,
    })),
    report,
    incidents: [incident],
    storage: {
      label: "Local sample data",
      detail: "This localhost page uses built-in incident data. The deployed workspace stores live runs.",
    },
    reasoning: {
      label: "Structured log-and-retrieval graph",
      detail: "Localhost uses the built-in intake, collector, retrieval, triage, and supervisor flow unless the hosted API is available.",
    },
    graph_trace: [
      { node: "intake", detail: "Alert replay normalized into the incident workflow." },
      { node: "collector-agent", detail: "Bundled logs were selected for the alert class." },
      { node: "retrieval-agent", detail: "Bundled incident examples were scanned for matching patterns." },
      { node: "triage-agent", detail: "Built-in logic assessed likely issue and evidence from logs and retrieved context." },
      { node: "supervisor-agent", detail: "Built-in response synthesis prepared the operator handoff." },
    ],
  };
}

async function refreshHealth() {
  try {
    const health = await fetchJson("/api/health");
    renderStorageStatus(health.storage);
    renderCombinedReasoning(health.reasoning, health.retrieval);
  } catch (_error) {
    renderStorageStatus({
      label: "API not connected",
      detail: "The product walkthrough is available, but the serverless backend is not responding yet.",
    });
    renderCombinedReasoning({
      label: "Structured log-and-retrieval graph",
      detail: "The local page is using the built-in intake, collector, retrieval, triage, and supervisor flow.",
    });
  }
}

async function refreshRecentRuns() {
  try {
    const payload = await fetchJson("/api/incidents");
    renderRecentRuns(payload.incidents || []);
    renderStorageStatus(payload.storage);
    renderLatestIncident(payload.incidents?.[0]);
  } catch (_error) {
    renderRecentRuns([]);
  }
}

async function loadIncidentDetail(incidentId) {
  const payload = await fetchJson(`/api/incidents/${incidentId}`);
  renderIncidentDetail(payload);
  renderLatestIncident(payload.incident);
}

async function runSandboxScenario() {
  const scenarioKey = document.getElementById("sandbox-scenario")?.value || "database";
  const severityMode = document.getElementById("sandbox-severity")?.value || "auto";
  const volumeMode = document.getElementById("sandbox-volume")?.value || "auto";
  const integration = getSelectedIntegration();

  renderScenario(scenarioKey);
  setText("sandbox-status", "Running live workflow");
  renderSandboxLog([integration.submitLabel]);

  try {
    const payload = await fetchJson("/api/run-scenario", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        scenario: scenarioKey,
        severity: severityMode,
        volume: volumeMode,
        ingestion_source: integration.key,
      }),
    });

    setText("sandbox-headline", payload.preview.headline);
    setText("sandbox-status", payload.preview.status);
    setText("sandbox-summary", payload.preview.summary);
    setText("sandbox-outcome", payload.preview.outcome);
    renderSandboxLog(extendLogWithGraphTrace(payload.preview.log, payload.graph_trace));
    renderStorageStatus(payload.storage);
    renderCombinedReasoning({
      label: payload.analysis_mode === "gemini-agent-graph" ? "Gemini log-and-retrieval graph active" : "Structured log-and-retrieval graph",
      detail:
        payload.analysis_mode === "gemini-agent-graph"
          ? "This incident was generated through the hosted intake, collector, retrieval, triage-agent, and supervisor-agent flow."
          : "This incident was generated through the built-in structured incident workflow.",
    }, payload.report?.retrieval?.summary);
    renderRecentRuns(payload.incidents || []);
    renderLatestIncident(payload.incident);
    renderIncidentDetail(payload);
  } catch (_error) {
    const fallback = localPreviewForScenario(scenarioKey, severityMode, volumeMode);
    setText("sandbox-headline", fallback.preview.headline);
    setText("sandbox-status", fallback.preview.status);
    setText("sandbox-summary", fallback.preview.summary);
    setText("sandbox-outcome", fallback.preview.outcome);
    renderSandboxLog(extendLogWithGraphTrace(fallback.preview.log, fallback.graph_trace));
    renderStorageStatus(fallback.storage);
    renderCombinedReasoning(fallback.reasoning);
    renderRecentRuns(fallback.incidents);
    renderLatestIncident(fallback.incident);
    renderIncidentDetail(fallback);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(getStoredTheme() || "light");

  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    persistTheme(nextTheme);
  });

  document.querySelectorAll(".integration-button").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveIntegration(button.dataset.integration);
      renderScenario(document.getElementById("sandbox-scenario")?.value || "database");
    });
  });

  document.querySelectorAll(".scenario-chip").forEach((button) => {
    button.addEventListener("click", () => renderScenario(button.dataset.scenario));
  });

  document.getElementById("run-sandbox")?.addEventListener("click", runSandboxScenario);
  document.getElementById("open-workflow")?.addEventListener("click", () => {
    const scenarioKey = document.getElementById("sandbox-scenario")?.value || "database";
    renderScenario(scenarioKey);
    document.getElementById("interactive-demo")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.getElementById("recent-runs")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-incident-id]");
    if (!button) return;
    loadIncidentDetail(button.dataset.incidentId).catch(() => {});
  });

  setActiveIntegration("cloudwatch");
  renderScenario("database");
  refreshHealth();
  refreshRecentRuns();
});
