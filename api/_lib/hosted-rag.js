import { embedText, getEmbeddingConfig } from "./gemini-embeddings.js";
import { retrieveIncidentExamples as retrieveBundledExamples } from "./rag-retriever.js";
import { hasSupabaseConfig, supabaseFetch } from "./storage.js";

function hasVectorSearchConfig() {
  return Boolean(process.env.GEMINI_API_KEY && hasSupabaseConfig());
}

function getRpcName() {
  return process.env.SUPABASE_VECTOR_RPC || "match_rag_documents";
}

function normalizeResult(row) {
  const metadata = row.metadata || {};
  return {
    id: row.id,
    content: row.content,
    doc_type: row.doc_type || metadata.doc_type || "knowledge",
    title: row.title || metadata.title || "Knowledge document",
    pattern: metadata.pattern || null,
    root_cause: metadata.root_cause || metadata.summary || row.content,
    mitigation: metadata.mitigation || metadata.next_steps || [],
    source: row.source || metadata.source || "supabase-vector",
    similarity: row.similarity ?? null,
    match_count: metadata.match_count || null,
    metadata,
  };
}

async function retrieveFromSupabaseVector(corpus, limit) {
  const embedding = await embedText(corpus, "RETRIEVAL_QUERY");
  const rows = await supabaseFetch(`/rpc/${getRpcName()}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: process.env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    },
    body: JSON.stringify({
      query_embedding: embedding,
      match_count: limit,
    }),
  });

  return (rows || []).map(normalizeResult);
}

export function getHostedRagSummary() {
  if (!hasVectorSearchConfig()) {
    return {
      mode: "bundled-rag",
      label: "Bundled retrieval corpus",
      detail: "The workflow uses bundled incident examples until Supabase vector retrieval is configured.",
    };
  }

  const { model, dimensions } = getEmbeddingConfig();
  return {
    mode: "supabase-vector-rag",
    label: "External vector retrieval enabled",
    detail: `The workflow queries Supabase pgvector using ${model} embeddings (${dimensions} dimensions).`,
  };
}

export async function retrieveGroundingContext(corpus, limit = 3) {
  if (!hasVectorSearchConfig()) {
    return {
      source: "bundled-rag",
      results: await retrieveBundledExamples(corpus, limit),
    };
  }

  try {
    const results = await retrieveFromSupabaseVector(corpus, limit);
    return {
      source: "supabase-vector-rag",
      results,
    };
  } catch (_error) {
    return {
      source: "bundled-rag",
      results: await retrieveBundledExamples(corpus, limit),
    };
  }
}
