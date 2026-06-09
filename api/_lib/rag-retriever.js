import { readFile } from "node:fs/promises";
import path from "node:path";

const EXAMPLES_FILE = path.join(process.cwd(), "app", "rag", "data", "examples.jsonl");

let exampleCache = null;

async function loadExamples() {
  if (exampleCache) {
    return exampleCache;
  }

  const raw = await readFile(EXAMPLES_FILE, "utf8");
  exampleCache = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  return exampleCache;
}

export async function retrieveIncidentExamples(corpus, limit = 3) {
  const examples = await loadExamples();
  const matches = examples
    .map((example) => {
      const pattern = example.pattern;
      if (!pattern) {
        return null;
      }
      const hitCount = (corpus.match(new RegExp(pattern, "gi")) || []).length;
      if (!hitCount) {
        return null;
      }
      return {
        ...example,
        match_count: hitCount,
      };
    })
    .filter(Boolean)
    .sort((left, right) => right.match_count - left.match_count);

  return matches.slice(0, limit);
}
