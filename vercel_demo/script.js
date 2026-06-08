import { SCENARIOS, getScenario } from "./scenarios.js";

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
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

function renderScenario(key) {
  const scenario = getScenario(key);

  document.querySelectorAll(".scenario-chip").forEach((button) => {
    const isActive = button.dataset.scenario === key;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  setText("scenario-title", scenario.title);
  setText("scenario-source", scenario.source);
  setText("scenario-repeats", `${scenario.occurrenceCount}x`);
  setText("scenario-priority", scenario.priority);
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
  renderList("output-evidence", scenario.evidence);
  renderList("output-next-steps", scenario.nextSteps);
  renderSteps(scenario.steps);
}

function renderIncidentDetail({ incident, steps = [], report = null }) {
  if (!incident) return;

  setText("scenario-title", incident.title || incident.service || "Incident");
  setText("scenario-source", incident.source || "Unknown");
  setText("scenario-repeats", `${incident.occurrence_count || 1}x`);
  setText("scenario-priority", incident.escalation_priority || "Monitor");
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
    source: scenario.source,
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
    evidence: scenario.evidence,
    next_steps: scenario.nextSteps,
  };

  return {
    preview: {
      headline: `${severityLabel} ${scenario.title}`,
      status: "Local sample response",
      summary: `${scenario.summary} This local page is showing a full incident response for ${repeatLabel}.`,
      outcome: scenario.action,
      log: [
        `Created a local sample incident for ${scenario.service}.`,
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
  };
}

async function refreshHealth() {
  try {
    const health = await fetchJson("/api/health");
    renderStorageStatus(health.storage);
  } catch (_error) {
    renderStorageStatus({
      label: "API not connected",
      detail: "The product walkthrough is available, but the serverless backend is not responding yet.",
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

  renderScenario(scenarioKey);
  setText("sandbox-status", "Running live workflow");
  renderSandboxLog(["Submitting scenario to the hosted app..."]);

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
      }),
    });

    setText("sandbox-headline", payload.preview.headline);
    setText("sandbox-status", payload.preview.status);
    setText("sandbox-summary", payload.preview.summary);
    setText("sandbox-outcome", payload.preview.outcome);
    renderSandboxLog(payload.preview.log);
    renderStorageStatus(payload.storage);
    renderRecentRuns(payload.incidents || []);
    renderLatestIncident(payload.incident);
    renderIncidentDetail(payload);
  } catch (_error) {
    const fallback = localPreviewForScenario(scenarioKey, severityMode, volumeMode);
    setText("sandbox-headline", fallback.preview.headline);
    setText("sandbox-status", fallback.preview.status);
    setText("sandbox-summary", fallback.preview.summary);
    setText("sandbox-outcome", fallback.preview.outcome);
    renderSandboxLog(fallback.preview.log);
    renderStorageStatus(fallback.storage);
    renderRecentRuns(fallback.incidents);
    renderLatestIncident(fallback.incident);
    renderIncidentDetail(fallback);
  }
}

document.addEventListener("DOMContentLoaded", () => {
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

  renderScenario("database");
  refreshHealth();
  refreshRecentRuns();
});
