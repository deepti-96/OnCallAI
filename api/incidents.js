import { listRecentIncidents, getStorageSummary } from "./_lib/storage.js";

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    const incidents = await listRecentIncidents(8);
    return res.status(200).json({
      incidents,
      storage: getStorageSummary(),
    });
  } catch (error) {
    return res.status(500).json({
      error: "Failed to load incidents",
      detail: error.message,
    });
  }
}
