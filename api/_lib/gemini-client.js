function hasGeminiConfig() {
  return Boolean(process.env.GEMINI_API_KEY);
}

function getGeminiModel() {
  return process.env.GEMINI_MODEL || "gemini-2.5-flash";
}

function getGeminiEndpoint() {
  return `https://generativelanguage.googleapis.com/v1beta/models/${getGeminiModel()}:generateContent`;
}

function extractJsonText(payload) {
  return (
    payload?.candidates?.[0]?.content?.parts
      ?.map((part) => part?.text || "")
      .join("")
      .trim() || ""
  );
}

export function hasGeminiReasoning() {
  return hasGeminiConfig();
}

export function getGeminiReasoningModel() {
  return getGeminiModel();
}

export async function generateGeminiJson({ systemInstruction, prompt, schema }) {
  const response = await fetch(getGeminiEndpoint(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": process.env.GEMINI_API_KEY,
    },
    body: JSON.stringify({
      systemInstruction: {
        parts: [{ text: systemInstruction }],
      },
      contents: [
        {
          role: "user",
          parts: [{ text: prompt }],
        },
      ],
      generationConfig: {
        temperature: 0.2,
        responseMimeType: "application/json",
        responseSchema: schema,
      },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Gemini request failed (${response.status}): ${body}`);
  }

  const payload = await response.json();
  const text = extractJsonText(payload);
  if (!text) {
    throw new Error("Gemini response did not include JSON content");
  }

  return JSON.parse(text);
}
