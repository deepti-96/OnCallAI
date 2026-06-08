# OnCallAI

OnCallAI is an AI-powered incident triage and root cause analysis prototype for DevOps and SRE workflows. It ingests alerts or incidents, gathers surrounding context, analyzes logs, records agent activity, computes escalation guidance, and produces a structured incident report through a lightweight Streamlit interface.

This project is designed as an explainable, hackathon-friendly foundation for building an autonomous on-call assistant. The current implementation focuses on local execution, deterministic workflows, and a clear architecture that can be extended with real alert sources, richer retrieval, and production-grade orchestration.

The repository now also includes a Vercel-friendly web experience with serverless API routes and a free-tier durable storage path for live hosted demos.

## Why OnCallAI

Modern on-call teams lose time switching between alerts, logs, dashboards, and tribal knowledge. OnCallAI aims to shorten that path by centralizing the first-response workflow:

- Accept an incident record.
- Collect relevant operational context.
- Analyze available logs and evidence.
- Generate an RCA-style summary with suggested mitigations.
- Expose the full processing trail in a transparent UI.

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
- Free-tier durable storage option through Supabase Postgres for hosted scenario runs.

## Architecture

OnCallAI follows a simple agent-inspired pipeline:

1. `runner` polls for incidents with `OPEN` status.
2. The collector stage retrieves context and logs for the incident.
3. The analyst stage evaluates evidence and drafts findings.
4. The supervisor stage writes the final report, includes escalation guidance, and marks the incident complete.
5. The UI reads the persisted data and displays incident state, steps, and outputs.

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
- [`api/`](api): Vercel serverless functions for hosted scenario execution and incident retrieval.
- [`vercel_demo/`](vercel_demo): Product-style web frontend for the Vercel deployment path.
- [`supabase/schema.sql`](supabase/schema.sql): Durable hosted schema for the free-tier Postgres setup.
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
├── api/                # Vercel serverless functions
├── supabase/           # Hosted Postgres schema for durable storage
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
- Optional OpenAI and AWS integrations via environment configuration
- Vercel serverless functions for the hosted web app
- Supabase Postgres on the free tier for durable hosted incident storage

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
- `OPENAI_API_KEY` if you plan to extend the project with hosted models

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

1. The frontend served from `vercel_demo/` runs on Vercel.
2. The `Try Product` flow calls Vercel API routes in `api/`.
3. Those API routes create incidents, steps, and reports for demo scenarios.
4. If Supabase credentials are present, the data is stored durably in Postgres.
5. If credentials are missing, the app falls back to local preview storage for local development only.

### Supabase setup

1. Create a free Supabase project.
2. Open the SQL editor.
3. Run the schema in [`supabase/schema.sql`](supabase/schema.sql).
4. In Vercel project settings, add:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
5. Redeploy the Vercel app.

After that, live scenario runs from the website are durably stored and can be reloaded in the hosted UI.

### Vercel setup

1. Import the GitHub repo into Vercel.
2. Keep the framework preset as `Other`.
3. Set the root directory to the repository root.
4. Add the Supabase environment variables above.
5. Deploy.

The site root is handled by [`vercel.json`](vercel.json), which serves the product UI from [`vercel_demo/index.html`](vercel_demo/index.html) and keeps `/api/*` available for the serverless backend.

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
- The Vercel product site can also run scenarios end to end and persist them in Supabase when deployed with the free-tier hosted stack.

This makes the project easy to demo, debug, and extend locally.

## Current Scope and Limitations

This repository is best understood as a strong prototype rather than a production-ready incident response platform.

- The default runner is intentionally lightweight and optimized for local demos rather than background job scale.
- The analyst uses lightweight local retrieval rather than a full production retrieval pipeline or LLM-backed reasoning engine.
- CloudWatch support is AWS-focused today; broader provider coverage and richer historical correlation can be extended further.
- Authentication, authorization, retries, and multi-tenant concerns are not implemented.
- The UI is optimized for local inspection and demos rather than operational scale.
- The Vercel-hosted path is intentionally scenario-driven today; it demonstrates the workflow cleanly, but it does not yet replace the richer local Streamlit operator console.

## Extension Ideas

Good next steps for evolving OnCallAI include:

- Connect real alert providers such as CloudWatch, PagerDuty, or Opsgenie.
- Replace heuristic analysis with retrieval-backed or model-backed reasoning.
- Add incident enrichment from dashboards, deploy metadata, and service ownership data.
- Introduce broader correlation across multiple signals and incidents.
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
