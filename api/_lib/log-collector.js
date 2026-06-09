import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { BUNDLED_LOGS } from "./bundled-demo-data.js";

const LOG_ROOT = path.join(process.cwd(), "app", "logs");

function chooseLogFolder({ incident, scenario }) {
  const signal = [
    incident?.service,
    incident?.title,
    incident?.source,
    incident?.alarm_name,
    scenario?.title,
    scenario?.summary,
    scenario?.trigger,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (/(db|database|sql|postgres|mysql|latency)/i.test(signal)) {
    return "db";
  }
  if (/(cpu|oom|infra|memory|node|host)/i.test(signal)) {
    return "infra";
  }
  return "web";
}

async function readLogFiles(folder) {
  const targetDir = path.join(LOG_ROOT, folder);
  try {
    const entries = await readdir(targetDir);
    const files = entries.filter((entry) => entry.endsWith(".log")).sort().slice(0, 5);
    const logs = await Promise.all(
      files.map(async (fileName) => {
        const absolutePath = path.join(targetDir, fileName);
        const content = await readFile(absolutePath, "utf8");
        return {
          file_name: fileName,
          snippet: content.slice(0, 5000),
        };
      }),
    );
    return logs;
  } catch (_error) {
    return BUNDLED_LOGS[folder] || [];
  }
}

export async function collectIncidentLogs({ incident, scenario }) {
  const folder = chooseLogFolder({ incident, scenario });
  const logs = await readLogFiles(folder);
  return {
    folder,
    logs,
  };
}
