import { generateGeminiJson, getGeminiReasoningModel, hasGeminiReasoning } from "./gemini-client.js";
import { collectIncidentLogs } from "./log-collector.js";
import { getHostedRagSummary, retrieveGroundingContext } from "./hosted-rag.js";

function getTimestamp(offset = 0) {
  return new Date(Date.now() + offset * 1000).toISOString();
}

function getTriageSchema() {
  return {
    type: "OBJECT",
    properties: {
      incident_summary: { type: "STRING" },
      likely_issue: { type: "STRING" },
      root_cause_hypothesis: { type: "STRING" },
      operational_impact: { type: "STRING" },
      trigger_signal: { type: "STRING" },
      evidence: {
        type: "ARRAY",
        items: { type: "STRING" },
      },
      next_checks: {
        type: "ARRAY",
        items: { type: "STRING" },
      },
      confidence: { type: "NUMBER" },
    },
    required: [
      "incident_summary",
      "likely_issue",
      "root_cause_hypothesis",
      "operational_impact",
      "trigger_signal",
      "evidence",
      "next_checks",
      "confidence",
    ],
  };
}

function getSupervisorSchema() {
  return {
    type: "OBJECT",
    properties: {
      headline: { type: "STRING" },
      escalation_priority: { type: "STRING" },
      escalation_target: { type: "STRING" },
      recommended_action: { type: "STRING" },
      operator_brief: { type: "STRING" },
      timeline_summary: { type: "STRING" },
      handoff_note: { type: "STRING" },
    },
    required: [
      "headline",
      "escalation_priority",
      "escalation_target",
      "recommended_action",
      "operator_brief",
      "timeline_summary",
      "handoff_note",
    ],
  };
}

function buildTriagePrompt({ incident, scenario, report }) {
  return `Analyze this alert-driven incident for an on-call engineer.

Incident:
${JSON.stringify(incident, null, 2)}

Known scenario context:
${JSON.stringify(
    {
      service: scenario.service,
      source: scenario.source,
      owner_team: scenario.ownerTeam,
      alarm_name: scenario.alarmName,
      summary_hint: scenario.summary,
      impact_hint: scenario.impact,
      trigger_hint: scenario.trigger,
      evidence_hint: scenario.evidence,
      next_steps_hint: scenario.nextSteps,
    },
    null,
    2,
  )}

Current built-in report:
${JSON.stringify(report.report, null, 2)}

Return concise JSON for the triage agent only.`;
}

function buildRetrievalCorpus({ incident, scenario, report, collected }) {
  const logText = (collected?.logs || []).map((log) => log.snippet).join("\n");
  return [
    incident.service,
    incident.title,
    incident.source,
    incident.alarm_name,
    incident.summary,
    scenario.summary,
    scenario.trigger,
    report.report.issue,
    report.report.root_cause,
    logText,
  ]
    .filter(Boolean)
    .join("\n")
    .slice(0, 20000);
}

function buildSupervisorPrompt({ incident, triage }) {
  return `You are the supervisor agent preparing the final operator handoff for this incident.

Incident:
${JSON.stringify(incident, null, 2)}

Triage agent output:
${JSON.stringify(triage, null, 2)}

Return concise JSON for the operator-facing response.`;
}

function addAgentStep({ incidentId, phase, description, detail, offset }) {
  return {
    id: crypto.randomUUID(),
    incident_id: incidentId,
    phase,
    description,
    detail,
    status: "completed",
    created_at: getTimestamp(offset),
  };
}

function buildFallbackGraph(run) {
  return {
    ...run,
    analysis_mode: "rules-demo",
    graph_trace: [
      {
        node: "intake",
        status: "completed",
        detail: "Alert replay normalized into the incident workflow.",
      },
      {
        node: "collector-agent",
        status: "completed",
        detail: "Bundled incident logs were selected for the alert class.",
      },
      {
        node: "retrieval-agent",
        status: "completed",
        detail: "Bundled incident examples were scanned for matching patterns.",
      },
      {
        node: "triage-agent",
        status: "completed",
        detail: "Built-in incident reasoning prepared the likely issue from logs and retrieved context.",
      },
      {
        node: "supervisor-agent",
        status: "completed",
        detail: "Built-in response synthesis prepared the operator handoff.",
      },
    ],
  };
}

async function runCollectorAgent(state) {
  const collected = await collectIncidentLogs(state);
  return {
    ...state,
    collected,
    graph_trace: [
      ...state.graph_trace,
      {
        node: "collector-agent",
        status: "completed",
        detail: `Collected ${collected.logs.length} log snippet(s) from the ${collected.folder} log bundle.`,
      },
    ],
  };
}

async function runRetrievalAgent(state) {
  const corpus = buildRetrievalCorpus(state);
  const retrieval = await retrieveGroundingContext(corpus);
  const retrievedExamples = retrieval.results;
  return {
    ...state,
    retrievedExamples,
    retrievalCorpus: corpus,
    retrievalSource: retrieval.source,
    graph_trace: [
      ...state.graph_trace,
      {
        node: "retrieval-agent",
        status: "completed",
        detail: retrievedExamples.length
          ? `Retrieved ${retrievedExamples.length} matching grounding document(s) from ${retrieval.source}.`
          : `No strong grounding documents matched the current incident corpus from ${retrieval.source}.`,
      },
    ],
  };
}

async function runTriageAgent(state) {
  const triage = await generateGeminiJson({
    systemInstruction:
      "You are an incident triage agent for DevOps/SRE workflows. Work from the alert, context, and evidence. Respond with concise JSON only.",
    prompt: `${buildTriagePrompt(state)}

Collected logs:
${JSON.stringify(state.collected, null, 2)}

Retrieved examples:
${JSON.stringify(state.retrievedExamples, null, 2)}
`,
    schema: getTriageSchema(),
  });

  return {
    ...state,
    triage,
    graph_trace: [
      ...state.graph_trace,
      {
        node: "triage-agent",
        status: "completed",
        detail: triage.incident_summary,
      },
    ],
  };
}

async function runSupervisorAgent(state) {
  const supervisor = await generateGeminiJson({
    systemInstruction:
      "You are a supervisor agent preparing the final operator response for an incident workspace. Respond with concise JSON only.",
    prompt: buildSupervisorPrompt(state),
    schema: getSupervisorSchema(),
  });

  return {
    ...state,
    supervisor,
    graph_trace: [
      ...state.graph_trace,
      {
        node: "supervisor-agent",
        status: "completed",
        detail: supervisor.operator_brief,
      },
    ],
  };
}

function finalizeGraph(state) {
  const triage = state.triage;
  const supervisor = state.supervisor;
  const extraSteps = [
    addAgentStep({
      incidentId: state.incident.id,
      phase: "graph/collector-agent",
      description: "Collector agent gathered incident log context",
      detail: `Selected ${state.collected.folder} logs and loaded ${state.collected.logs.length} snippet(s).`,
      offset: state.steps.length,
    }),
    addAgentStep({
      incidentId: state.incident.id,
      phase: "graph/retrieval-agent",
      description: "Retrieval agent matched incident examples",
      detail: state.retrievedExamples.length
        ? `Retrieved ${state.retrievedExamples.length} grounding document(s) from ${state.retrievalSource}.`
        : `No matching grounding document was retrieved from ${state.retrievalSource}.`,
      offset: state.steps.length + 1,
    }),
    addAgentStep({
      incidentId: state.incident.id,
      phase: "graph/triage-agent",
      description: "Triage agent assessed likely issue and evidence",
      detail: triage.incident_summary,
      offset: state.steps.length + 2,
    }),
    addAgentStep({
      incidentId: state.incident.id,
      phase: "graph/supervisor-agent",
      description: "Supervisor agent prepared the operator handoff",
      detail: supervisor.operator_brief,
      offset: state.steps.length + 3,
    }),
  ];

  const updatedIncident = {
    ...state.incident,
    escalation_priority: supervisor.escalation_priority || state.incident.escalation_priority,
    escalation_target: supervisor.escalation_target || state.incident.escalation_target,
    owner_team: supervisor.escalation_target || state.incident.owner_team,
    summary: triage.incident_summary || state.incident.summary,
    updated_at: new Date().toISOString(),
  };

  return {
    ...state,
    incident: updatedIncident,
    steps: [...state.steps, ...extraSteps],
    report: {
      ...state.report,
      report: {
        ...state.report.report,
        headline: supervisor.headline,
        issue: triage.likely_issue,
        root_cause: triage.root_cause_hypothesis,
        recommended_action: supervisor.recommended_action,
        impact: triage.operational_impact,
        trigger: triage.trigger_signal,
        evidence: triage.evidence,
        next_steps: triage.next_checks,
        summary: triage.incident_summary,
        confidence: triage.confidence,
        log_context: state.collected,
        retrieved_examples: state.retrievedExamples,
        retrieval: {
          source: state.retrievalSource,
          summary: getHostedRagSummary(),
        },
        operator_brief: supervisor.operator_brief,
        handoff_note: supervisor.handoff_note,
        timeline_summary: supervisor.timeline_summary,
        escalation_priority: supervisor.escalation_priority,
        escalation_target: supervisor.escalation_target,
        analysis_mode: "gemini-agent-graph",
        reasoning_model: getGeminiReasoningModel(),
      },
    },
    analysis_mode: "gemini-agent-graph",
  };
}

export async function runIncidentAgentGraph(run) {
  if (!hasGeminiReasoning()) {
    return buildFallbackGraph(run);
  }

  let state = {
    ...run,
    graph_trace: [
      {
        node: "intake",
        status: "completed",
        detail: "Alert replay normalized into the incident workflow.",
      },
    ],
  };

  state = await runCollectorAgent(state);
  state = await runRetrievalAgent(state);
  state = await runTriageAgent(state);
  state = await runSupervisorAgent(state);
  return finalizeGraph(state);
}
