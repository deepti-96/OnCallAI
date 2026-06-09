import { getReasoningSummary, getStorageSummary } from "./_lib/storage.js";
import { getHostedRagSummary } from "./_lib/hosted-rag.js";

export default function handler(_req, res) {
  res.status(200).json({
    ok: true,
    app: "OnCallAI",
    runtime: "vercel-functions",
    storage: getStorageSummary(),
    reasoning: getReasoningSummary(),
    retrieval: getHostedRagSummary(),
    setup: {
      provider: "Supabase",
      required_env: ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
      optional_env: [
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_EMBEDDING_MODEL",
        "GEMINI_EMBEDDING_DIMENSIONS",
        "SUPABASE_VECTOR_RPC",
      ],
    },
  });
}
