function getEmbeddingModel() {
  return process.env.GEMINI_EMBEDDING_MODEL || "gemini-embedding-001";
}

export function getEmbeddingConfig() {
  return {
    model: getEmbeddingModel(),
    dimensions: Number(process.env.GEMINI_EMBEDDING_DIMENSIONS || 3072),
  };
}

export async function embedText(text, taskType = "RETRIEVAL_QUERY") {
  const { model, dimensions } = getEmbeddingConfig();
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:embedContent`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": process.env.GEMINI_API_KEY,
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
    throw new Error(`Gemini embedding request failed (${response.status}): ${body}`);
  }

  const payload = await response.json();
  const values = payload?.embedding?.values;
  if (!Array.isArray(values) || !values.length) {
    throw new Error("Gemini embedding response did not include vector values");
  }
  return values;
}
