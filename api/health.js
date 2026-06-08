import { getStorageSummary } from "./_lib/storage.js";

export default function handler(_req, res) {
  res.status(200).json({
    ok: true,
    app: "OnCallAI",
    runtime: "vercel-functions",
    storage: getStorageSummary(),
    setup: {
      provider: "Supabase",
      required_env: ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
    },
  });
}
