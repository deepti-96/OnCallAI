import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const LOCAL_STORAGE_DIR = path.join(process.cwd(), ".local");
const LOCAL_STORAGE_FILE = path.join(LOCAL_STORAGE_DIR, "vercel-runs.json");

function hasSupabaseConfig() {
  return Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY);
}

function getHeaders(prefer = "") {
  const headers = {
    apikey: process.env.SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
  if (prefer) {
    headers.Prefer = prefer;
  }
  return headers;
}

function getBaseUrl() {
  return `${process.env.SUPABASE_URL.replace(/\/$/, "")}/rest/v1`;
}

async function readLocalState() {
  try {
    const raw = await readFile(LOCAL_STORAGE_FILE, "utf8");
    return JSON.parse(raw);
  } catch (error) {
    if (error.code === "ENOENT") {
      return { incidents: [], steps: [], reports: [] };
    }
    throw error;
  }
}

async function writeLocalState(state) {
  await mkdir(LOCAL_STORAGE_DIR, { recursive: true });
  await writeFile(LOCAL_STORAGE_FILE, JSON.stringify(state, null, 2));
}

async function supabaseFetch(endpoint, options = {}) {
  const response = await fetch(`${getBaseUrl()}${endpoint}`, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Supabase request failed (${response.status}): ${body}`);
  }
  if (response.status === 204) {
    return null;
  }
  const body = await response.text();
  if (!body) {
    return null;
  }
  return JSON.parse(body);
}

export function getStorageMode() {
  return hasSupabaseConfig() ? "supabase-postgres" : "local-preview";
}

export function getStorageSummary() {
  if (hasSupabaseConfig()) {
    return {
      mode: "supabase-postgres",
      label: "Durable storage connected",
      detail: "Runs are stored in Supabase Postgres.",
    };
  }

  return {
    mode: "local-preview",
    label: "Preview storage only",
    detail: "Runs are saved to a local JSON file until Supabase environment variables are added.",
  };
}

export async function saveScenarioRun({ incident, steps, report }) {
  if (!hasSupabaseConfig()) {
    const state = await readLocalState();
    state.incidents.push(incident);
    state.steps.push(...steps);
    state.reports.push(report);
    await writeLocalState(state);
    return incident;
  }

  await supabaseFetch("/incidents", {
    method: "POST",
    headers: getHeaders("return=representation"),
    body: JSON.stringify(incident),
  });
  await supabaseFetch("/incident_steps", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(steps),
  });
  await supabaseFetch("/incident_reports", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      id: report.id,
      incident_id: report.incident_id,
      created_at: report.created_at,
      report: report.report,
    }),
  });
  return incident;
}

export async function listRecentIncidents(limit = 6) {
  if (!hasSupabaseConfig()) {
    const state = await readLocalState();
    return [...state.incidents]
      .sort((left, right) => right.created_at.localeCompare(left.created_at))
      .slice(0, limit);
  }

  return supabaseFetch(
    `/incidents?select=id,service,title,status,severity,source,occurrence_count,escalation_priority,owner_team,created_at&order=created_at.desc&limit=${limit}`,
    {
      method: "GET",
      headers: getHeaders(),
    },
  );
}
