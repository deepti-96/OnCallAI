# OnCallAI

OnCallAI is an AI-powered incident triage and root cause analysis prototype for DevOps and SRE workflows. It ingests alerts or incidents, gathers surrounding context, analyzes logs, records agent activity, computes escalation guidance, and produces structured RCA-style reports and operator handoffs.

This project is designed as an explainable, hackathon-friendly foundation for building an autonomous on-call assistant. The current implementation has two complementary paths: a local Python pipeline optimized for deterministic development and testing, and a hosted Vercel agent graph that can use Gemini, bundled retrieval, and Supabase vector retrieval when configured.

The repository also includes a Vercel-friendly web experience with serverless API routes, a CloudWatch Alarm State Change-style event envelope, durable storage through Supabase Postgres, and bundled runtime fallbacks that keep the hosted demo usable even when filesystem-hosted logs are unavailable in serverless deployments.

## Why OnCallAI 

Modern on-call teams lose time switching between alerts, logs, dashboards, and tribal knowledge. OnCallAI aims to shorten that path by centralizing the first-response workflow:

- Accept an incident record.
- Collect relevant operational context.
- Analyze available logs and evidence.
- Generate an RCA-style summary with suggested mitigations.
- Expose the full processing trail in a transparent UI.
- Run a hosted collector, retrieval, triage, and supervisor workflow for live demos.

## Core Capabilities

- Incident intake backed by SQLite for simple local development.
- CloudWatch-style alert ingestion through simulator and JSON file entrypoints.
- Real CloudWatch alarm polling through a boto3-backed middleware adapter, including recovery-state ingestion.
- Alert deduplication for repeated alarms with occurrence tracking and recovery handling.
- Step-by-step execution tracking for collector, analyst, and supervisor stages.
- Retrieval-assisted log analysis that combines heuristic rules with example-based incident context.
- Escalation guidance that recommends paging targets, priority, and next action.
- Downloadable incident reports in both JSON and Markdown formats.
- Streamlit dashboard for filtering incidents, reviewing agent timelines, inspecting generated reports, and triaging stale or noisy alerts.
- Environment-based configuration for polling, models, logging mode, and optional cloud integrations.
- Vercel-compatible product site with interactive incident testing through serverless API routes.
- Hosted incident intake that generates a CloudWatch alarm envelope, CloudWatch log-source metadata, and persisted incident records.
- Hosted agent graph with intake, collector, retrieval, triage, and supervisor nodes.
- Optional Gemini structured JSON reasoning for hosted triage and operator handoff generation.
- Hosted RAG that falls back to bundled incident examples or uses Supabase pgvector when configured.
- Bundled runtime log and RAG fallbacks so the hosted app still runs even if serverless filesystem packaging is constrained.
- Realistic CloudWatch Alarm State Change replay and log source metadata in hosted scenarios.
- Free-tier durable storage option through Supabase Postgres for hosted scenario runs.

## Architecture

OnCallAI follows an agent-inspired workflow in both local and hosted modes.

### Local Python pipeline

1. `runner` polls for incidents with `OPEN` status.
2. The collector stage retrieves context and logs for the incident.
3. The analyst stage evaluates evidence and drafts findings.
4. The supervisor stage writes the final report, includes escalation guidance, and marks the incident complete.
5. The UI reads the persisted data and displays incident state, steps, and outputs.

### Hosted Vercel agent graph

1. `/api/run-scenario` creates a realistic incident scenario and a CloudWatch Alarm State Change-style event payload.
2. The collector agent loads matching log snippets plus CloudWatch log-group and stream-prefix metadata.
3. The retrieval agent retrieves grounding context from Supabase pgvector when available, or from bundled incident examples otherwise.
4. The triage agent produces the incident summary, likely issue, root-cause hypothesis, evidence, next checks, and confidence.
5. The supervisor agent produces the operator handoff, escalation priority, recommended action, timeline summary, and handoff note.
6. The run is stored in Supabase Postgres when configured, or in local preview storage for development.

If `GEMINI_API_KEY` is present, the hosted triage and supervisor agents use Gemini structured JSON output. If it is missing, the hosted flow falls back to built-in demo reasoning while preserving the same graph trace shape.

### Main Components

- [`app/runner.py`](app/runner.py): Main polling loop and incident execution flow.
- [`app/db/dal.py`](app/db/dal.py): Database access layer for incidents, steps, and reports.
- [`app/middleware/alert_normalizer.py`](app/middleware/alert_normalizer.py): CloudWatch-style alert normalization into the incident schema.
- [`app/middleware/alert_ingest.py`](app/middleware/alert_ingest.py): Ingestion path for normalized alerts.
- [`app/middleware/cloudwatch_boto.py`](app/middleware/cloudwatch_boto.py): Real CloudWatch polling and alarm-to-incident ingestion.
- [`app/models/escalation_policy.py`](app/models/escalation_policy.py): Escalation priority, paging, and operator action guidance.
- [`app/agents/collector_agent.py`](app/agents/collector_agent.py): Log selection and retrieval logic.
- [`app/agents/analyst_agent.py`](app/agents/analyst_agent.py): Retrieval-assisted analysis and mitigation generation.
- [`app/agents/supervisor.py`](app/agents/supervisor.py): Report compilation and workflow completion.
- [`ui/streamlit_app.py`](ui/streamlit_app.py): Operator-facing incident dashboard.
- [`api/`](api): Vercel serverless functions for hosted scenario execution, incident retrieval, agent graph orchestration, hosted RAG, and health checks.
- [`api/_lib/agent-graph.js`](api/_lib/agent-graph.js): Hosted collector, retrieval, triage, and supervisor graph.
- [`api/_lib/hosted-rag.js`](api/_lib/hosted-rag.js): Bundled retrieval and optional Supabase vector retrieval.
- [`api/_lib/gemini-client.js`](api/_lib/gemini-client.js): Gemini structured JSON reasoning client.
- [`api/_lib/gemini-embeddings.js`](api/_lib/gemini-embeddings.js): Gemini embedding client for hosted vector retrieval.
- [`api/_lib/cloudwatch-event.js`](api/_lib/cloudwatch-event.js): CloudWatch alarm event and log-source shaping for hosted scenarios.
- [`api/_lib/bundled-demo-data.js`](api/_lib/bundled-demo-data.js): Runtime-safe bundled log snippets and fallback incident examples for hosted serverless execution.
- [`vercel_demo/`](vercel_demo): Product-style web frontend for the Vercel deployment path.
- [`supabase/schema.sql`](supabase/schema.sql): Durable hosted schema for the free-tier Postgres setup.
- [`supabase/vector_rag.sql`](supabase/vector_rag.sql): Optional pgvector schema and matching RPC for hosted RAG.
- [`app/db/schema.sql`](app/db/schema.sql): SQLite schema for incidents, agent steps, and reports.
- [`tests/`](tests): Lightweight unit and flow tests using `unittest`.

## Repository Structure

```text
OnCallAI/
├── app/
│   ├── agents/         # Collector, analyst, and supervisor logic
│   ├── db/             # Schema and data access layer
│   ├── middleware/     # Alert normalization, ingestion, and CloudWatch adapters
│   ├── rag/            # RAG-related stubs and loaders
│   ├── config.py       # Environment-driven configuration
│   └── runner.py       # Main incident processing loop
├── rag_pipeline/       # Experimental retrieval pipeline components
├── scripts/            # Seeding and local setup helpers
├── api/                # Vercel serverless functions and hosted agent graph
├── supabase/           # Hosted Postgres and optional pgvector schemas
├── tests/              # Lightweight unit and incident-flow tests
├── ui/                 # Streamlit application
├── vercel_demo/        # Vercel-friendly product website
├── Makefile
├── requirements.txt
└── README.md
```

## Tech Stack

- Python 3
- Streamlit
- SQLite
- SQLAlchemy
- LangChain and LangGraph dependencies for future orchestration expansion
- Chroma / FAISS / Pinecone libraries for retrieval experimentation
- Optional AWS integrations via environment configuration
- Vercel serverless functions for the hosted web app and agent graph
- Gemini generateContent for hosted structured triage and supervisor reasoning
- Gemini embeddings for optional hosted vector retrieval
- Supabase Postgres on the free tier for durable hosted incident storage
- Supabase pgvector for optional hosted RAG

## Getting Started

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

At minimum, review these values in `.env`:

- `POLL_INTERVAL_SECONDS`
- `DB_URL`
- `LOGS_LOCAL_ROOT`
- `USE_REAL_CLOUDWATCH`
- `GEMINI_API_KEY` if you want the hosted Vercel agent graph to use Gemini reasoning

### 4. Seed local demo data

```bash
make seed
```

This populates sample incident data and uses the bundled log examples already stored in the repository.

### 5. Ingest a sample alert

```bash
make simulate-alert
```

You can also ingest a saved CloudWatch-style JSON payload directly:

```bash
python3 scripts/ingest_alert.py path/to/alert.json
```

### 6. Poll real CloudWatch alarms

If you have AWS credentials configured and want to ingest live alarms:

```bash
make poll-cloudwatch
```

This polls current alarms in the `ALARM` and `OK` states, normalizes them, and routes them through the same ingestion and deduplication path as local alert payloads.

### 7. Start the incident runner

```bash
make run
```

### 8. Launch the UI

In a separate terminal:

```bash
make ui
```

### 9. Run tests

```bash
make test
```

## Free-Tier Hosted Stack

The simplest free hosted version of OnCallAI uses:

- Vercel Hobby for the website and serverless API routes
- Supabase Free for durable Postgres storage

This is the safest path if you want a public product site and a live scenario flow without relying on SQLite in a deployed container.

### Hosted architecture

1. The product overview page and live workspace run on Vercel.
2. The hosted workspace calls Vercel API routes in `api/`.
3. Those API routes create incidents, steps, and reports for CloudWatch-style demo scenarios.
4. If Supabase credentials are present, the data is stored durably in Postgres.
5. If credentials are missing, the app falls back to local preview storage for local development only.
6. If Gemini is configured, hosted scenarios run the Gemini-backed collector, retrieval, triage, and supervisor graph. Otherwise they run in rules-demo mode.
7. If Supabase vector RAG is configured, hosted scenarios retrieve grounding documents from pgvector. Otherwise they use bundled examples.
8. If filesystem-hosted demo logs are unavailable in the serverless runtime, the API falls back to bundled log and incident-example data so the hosted workflow stays usable.

### Supabase setup

1. Create a free Supabase project.
2. Open the SQL editor.
3. Run the schema in [`supabase/schema.sql`](supabase/schema.sql).
4. Optional: run [`supabase/vector_rag.sql`](supabase/vector_rag.sql) if you want hosted vector retrieval.
5. In Vercel project settings, add:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
6. Optional: add the Gemini variables for hosted model reasoning and vector retrieval:
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL`
   - `GEMINI_EMBEDDING_MODEL`
   - `GEMINI_EMBEDDING_DIMENSIONS=3072`
   - `SUPABASE_VECTOR_RPC=match_rag_documents`
7. Redeploy the Vercel app.

After that, live scenario runs from the website are durably stored and can be reloaded in the hosted UI.

To seed hosted vector RAG documents after creating the vector schema, run:

```bash
GEMINI_API_KEY=... \
SUPABASE_URL=... \
SUPABASE_SERVICE_ROLE_KEY=... \
GEMINI_EMBEDDING_DIMENSIONS=3072 \
node scripts/seed_supabase_rag.mjs
```

### Vercel setup

1. Import the GitHub repo into Vercel.
2. Keep the framework preset as `Other`.
3. Set the root directory to the repository root.
4. Add the Supabase environment variables above.
5. Deploy.

The site root is handled by [`vercel.json`](vercel.json), which keeps `/api/*` available for the serverless backend and bundles the hosted log and RAG assets for the Vercel runtime.

## Make Targets

```bash
make seed   # Seed sample data
make simulate-alert   # Ingest a sample CloudWatch-style alert
make poll-cloudwatch  # Poll live CloudWatch alarms and ingest them
make run    # Start incident polling and processing
make ui     # Launch the Streamlit app
make test   # Run the unit and incident-flow test suite
make clean  # Remove the local SQLite db and generated reports
```

## Configuration

The project is configured primarily through environment variables.

### Core

- `ENV`: Environment name, default `dev`
- `POLL_INTERVAL_SECONDS`: Runner poll interval

### LLM and Retrieval

- `OPENAI_API_KEY`: Optional API key for future LLM-backed flows
- `EMBEDDINGS_MODEL`: Embedding model identifier
- `LLM_MODEL`: Chat model identifier
- `VECTOR_BACKEND`: Retrieval backend, such as `chroma` or `faiss`
- `GEMINI_API_KEY`: Enables hosted Gemini triage and supervisor reasoning
- `GEMINI_MODEL`: Hosted Gemini reasoning model, defaults to `gemini-2.5-flash`
- `GEMINI_EMBEDDING_MODEL`: Hosted embedding model, defaults to `gemini-embedding-001`
- `GEMINI_EMBEDDING_DIMENSIONS`: Hosted embedding dimensions. Use `3072` with the current seeded pgvector setup.
- `SUPABASE_VECTOR_RPC`: Optional hosted vector search RPC name, defaults to `match_rag_documents`

### Database

- `DB_URL`: SQLAlchemy-style database URL for external integrations
- `DB_FILE`: SQLite file used by the local DAL, defaults to `dev.db`
- `SUPABASE_URL`: Supabase project URL for hosted durable storage
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase server-side key for Vercel API writes

### Logs and Cloud

- `LOGS_MODE`: `local` or `s3`
- `LOGS_LOCAL_ROOT`: Path to bundled local logs
- `USE_REAL_CLOUDWATCH`: Enables real CloudWatch integration when set to `true`
- `CLOUDWATCH_LOG_GROUP`: CloudWatch log group name
- `AWS_REGION`: AWS region for real CloudWatch polling
- `CLOUDWATCH_MAX_RECORDS`: Maximum number of alarms to fetch per polling cycle

## How the Demo Works

The current demo path is intentionally simple and transparent:

- Incidents are stored in SQLite.
- Alerts can be ingested from CloudWatch-style payloads through the simulator or JSON file entrypoint.
- Live CloudWatch alarms can also be polled through the boto3-backed middleware adapter.
- Repeated alarms are deduplicated into a single open incident with occurrence and last-seen tracking.
- Recovery events update the existing incident instead of creating a duplicate record.
- The runner picks up incidents with `OPEN` status.
- The runner dispatches the incident through collector, analyst, and supervisor stages.
- The analyst combines rule-based matching with retrieved examples from the bundled incident corpus.
- The supervisor attaches escalation guidance to the final report based on severity, age, service tier, and repeat volume.
- Agent steps are written back to the database as the incident is processed.
- Reports are stored in structured JSON plus Markdown.
- The UI reads directly from the database and lets you inspect repeat-alert triage signals, escalation guidance, alert metadata, timelines, payloads, and final reports.
- The hosted product site can also run scenarios end to end, replay CloudWatch Alarm State Change-style events, collect bundled logs, retrieve grounding context, run a hosted agent graph, and persist results in Supabase when deployed with the free-tier hosted stack.

This makes the project easy to demo, debug, and extend locally.

## Hosted Agent Modes

The hosted runtime is designed to degrade gracefully based on environment configuration.

| Mode | Requirements | Behavior |
| --- | --- | --- |
| `rules-demo` | No `GEMINI_API_KEY` | Uses built-in scenario reasoning while preserving the intake, collector, retrieval, triage, and supervisor trace. |
| `gemini-agent-graph` | `GEMINI_API_KEY` | Uses Gemini structured JSON output for triage and supervisor reasoning. |
| `bundled-rag` | Default retrieval mode | Retrieves matching examples from bundled incident patterns. |
| `supabase-vector-rag` | `GEMINI_API_KEY`, Supabase env vars, vector schema | Embeds the incident corpus and retrieves grounding documents through Supabase pgvector. |

The health endpoint at `/api/health` reports the active storage, reasoning, and retrieval modes.

## Current Scope and Limitations

This repository is best understood as a strong prototype rather than a production-ready incident response platform.

- The default runner is intentionally lightweight and optimized for local demos rather than background job scale.
- The analyst uses lightweight local retrieval rather than a full production retrieval pipeline or LLM-backed reasoning engine.
- CloudWatch support is the first concrete adapter. The hosted workspace currently replays CloudWatch-style alarm events rather than receiving live AWS alarms directly. PagerDuty, Datadog, Grafana, New Relic, Opsgenie, or custom anomaly detectors can be added by normalizing their events into the same incident schema.
- The hosted Gemini and vector RAG paths require external credentials and careful embedding-dimension alignment with the Supabase schema.
- Authentication, authorization, retries, and multi-tenant concerns are not implemented.
- The UI is optimized for local inspection and demos rather than operational scale.
- The Vercel-hosted path is intentionally scenario-driven today; it demonstrates the workflow cleanly, but it does not yet replace a full production incident console.

## Extension Ideas

Good next steps for evolving OnCallAI include:

- Connect real alert providers such as CloudWatch, PagerDuty, Datadog, Grafana, New Relic, or Opsgenie.
- Replace more heuristic analysis paths with retrieval-backed or model-backed reasoning.
- Add incident enrichment from dashboards, deploy metadata, and service ownership data.
- Introduce broader correlation across multiple signals and incidents.
- Formalize the local Python workflow with LangGraph for typed state, conditional routing, retries, and human review checkpoints.
- Add automated remediation suggestions with human approval gates.
- Expand the UI into a richer operations console with deeper search, collaboration, and audit views.

## Professional Use Cases

OnCallAI can be positioned as:

- A hackathon project focused on agentic operations tooling.
- A portfolio project demonstrating AI-assisted incident workflows.
- A prototype for internal SRE automation experiments.
- A foundation for future RCA copilots and on-call support systems.

## Contributing

If you are iterating on the project, a practical workflow is:

1. Create or seed incidents.
2. Run the processor locally.
3. Inspect output in the Streamlit UI.
4. Improve collection, analysis, or report generation logic.
5. Re-run with fresh sample data.

Keep changes small and test the runner and UI together when modifying core incident flow.

## License

This repository includes a [`LICENSE`](LICENSE) file at the root. Review it before external reuse or distribution.
