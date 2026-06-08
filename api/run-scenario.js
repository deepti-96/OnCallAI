import { buildScenarioRun } from "./_lib/scenario-runner.js";
import { getStorageSummary, listRecentIncidents, saveScenarioRun } from "./_lib/storage.js";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    const payload = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const run = buildScenarioRun(payload);
    await saveScenarioRun(run);
    const incidents = await listRecentIncidents(8);

    return res.status(200).json({
      storage: getStorageSummary(),
      incident: run.incident,
      steps: run.steps,
      report: run.report.report,
      preview: run.preview,
      incidents,
    });
  } catch (error) {
    return res.status(500).json({
      error: "Failed to run scenario",
      detail: error.message,
    });
  }
}
