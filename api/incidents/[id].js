import { getIncidentDetail, getStorageSummary } from "../_lib/storage.js";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ error: "Method not allowed" });
  }

  const incidentId = req.query?.id;
  if (!incidentId) {
    return res.status(400).json({ error: "Incident id is required" });
  }

  try {
    const detail = await getIncidentDetail(incidentId);
    if (!detail.incident) {
      return res.status(404).json({ error: "Incident not found" });
    }

    return res.status(200).json({
      ...detail,
      storage: getStorageSummary(),
    });
  } catch (error) {
    return res.status(500).json({
      error: "Failed to load incident detail",
      detail: error.message,
    });
  }
}
