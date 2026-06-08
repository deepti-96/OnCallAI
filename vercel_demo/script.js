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
        <article class="recent-run-card">
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
        </article>
      `,
    )
    .join("");
}

function renderStorageStatus(storage) {
  if (!storage) return;
  setText("storage-label", storage.label);
  setText("storage-detail", storage.detail);
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
  const repeatLabel =
    volumeMode === "auto" ? `${scenario.occurrenceCount} repeated alerts` : volumeMode === "repeat" ? "Repeated alerts" : "Single alert";

  return {
    preview: {
      headline: `${severityLabel} ${scenario.title}`,
      status: "Preview mode only",
      summary: `${scenario.summary} ${repeatLabel} will be shown in the workspace.`,
      outcome: scenario.action,
      log: [
        `Prepared ${severityLabel.toLowerCase()} preview for ${scenario.service}.`,
        `Showing ${repeatLabel.toLowerCase()} behavior in the incident workspace.`,
        "API is unavailable, so this run is not being durably stored yet.",
      ],
    },
    incidents: [],
    storage: {
      label: "Preview mode only",
      detail: "Local browser preview is active. Deploy the API and connect Supabase for durable live runs.",
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
  } catch (_error) {
    renderRecentRuns([]);
  }
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
  } catch (_error) {
    const fallback = localPreviewForScenario(scenarioKey, severityMode, volumeMode);
    setText("sandbox-headline", fallback.preview.headline);
    setText("sandbox-status", fallback.preview.status);
    setText("sandbox-summary", fallback.preview.summary);
    setText("sandbox-outcome", fallback.preview.outcome);
    renderSandboxLog(fallback.preview.log);
    renderStorageStatus(fallback.storage);
    renderRecentRuns(fallback.incidents);
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

  renderScenario("database");
  refreshHealth();
  refreshRecentRuns();
});
