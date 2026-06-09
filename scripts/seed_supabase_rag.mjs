import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const cwd = process.cwd();
const examplesFile = path.join(cwd, "app", "rag", "data", "examples.jsonl");
const logsRoot = path.join(cwd, "app", "logs");

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env: ${name}`);
  }
  return value;
}

function getSupabaseBaseUrl() {
  return `${requiredEnv("SUPABASE_URL").replace(/\/$/, "")}/rest/v1`;
}

function getHeaders() {
  const key = requiredEnv("SUPABASE_SERVICE_ROLE_KEY");
  return {
    "Content-Type": "application/json",
    apikey: key,
    Authorization: `Bearer ${key}`,
    Prefer: "resolution=merge-duplicates",
  };
}

function getEmbeddingConfig() {
  return {
    apiKey: requiredEnv("GEMINI_API_KEY"),
    model: process.env.GEMINI_EMBEDDING_MODEL || "gemini-embedding-001",
    dimensions: Number(process.env.GEMINI_EMBEDDING_DIMENSIONS || 768),
  };
}

async function embedText(text, taskType = "RETRIEVAL_DOCUMENT") {
  const { apiKey, model, dimensions } = getEmbeddingConfig();
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:embedContent`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": apiKey,
      },
      body: JSON.stringify({
        model: `models/${model}`,
        content: {
          parts: [{ text }],
        },
        embedContentConfig: {
          taskType,
          outputDimensionality: dimensions,
        },
      }),
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Gemini embedding failed (${response.status}): ${body}`);
  }

  const payload = await response.json();
  return payload?.embedding?.values;
}

async function loadExampleDocs() {
  const raw = await readFile(examplesFile, "utf8");
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const example = JSON.parse(line);
      const title = `Incident Pattern ${index + 1}`;
      const content = [
        `Pattern: ${example.pattern}`,
        `Root cause: ${example.root_cause}`,
        `Mitigation: ${(example.mitigation || []).join(", ")}`,
      ].join("\n");
      return {
        id: crypto.randomUUID(),
        title,
        content,
        doc_type: "incident-pattern",
        source: "seeded-example",
        metadata: example,
      };
    });
}

async function loadLogDocs() {
  const folders = await readdir(logsRoot);
  const docs = [];

  for (const folder of folders) {
    const folderPath = path.join(logsRoot, folder);
    const entries = (await readdir(folderPath)).filter((entry) => entry.endsWith(".log"));
    for (const entry of entries) {
      const content = await readFile(path.join(folderPath, entry), "utf8");
      docs.push({
        id: crypto.randomUUID(),
        title: `${folder} log ${entry}`,
        content,
        doc_type: "log-snippet",
        source: "seeded-log",
        metadata: {
          folder,
          file_name: entry,
        },
      });
    }
  }

  return docs;
}

async function upsertDocuments(documents) {
  const response = await fetch(`${getSupabaseBaseUrl()}/rag_documents`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(documents),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Supabase upsert failed (${response.status}): ${body}`);
  }
}

async function main() {
  const docs = [...(await loadExampleDocs()), ...(await loadLogDocs())];
  const embeddedDocs = [];

  for (const doc of docs) {
    const embedding = await embedText(doc.content);
    embeddedDocs.push({
      ...doc,
      embedding,
    });
  }

  await upsertDocuments(embeddedDocs);
  console.log(`Seeded ${embeddedDocs.length} RAG document(s) into Supabase.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
