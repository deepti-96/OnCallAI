# OnCallAI

OnCallAI is an AI-powered incident triage and root cause analysis prototype for DevOps and SRE workflows. It ingests alerts or incidents, gathers surrounding context, analyzes logs, records agent activity, and produces a structured incident report through a lightweight Streamlit interface.

This project is designed as an explainable, hackathon-friendly foundation for building an autonomous on-call assistant. The current implementation focuses on local execution, deterministic workflows, and a clear architecture that can be extended with real alert sources, richer retrieval, and production-grade orchestration.

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
- Real CloudWatch alarm polling through a boto3-backed middleware adapter.
- Step-by-step execution tracking for collector, analyst, and supervisor stages.
- Retrieval-assisted log analysis that combines heuristic rules with example-based incident context.
- Downloadable incident reports in both JSON and Markdown formats.
- Streamlit dashboard for filtering incidents, reviewing agent timelines, and inspecting generated reports.
- Environment-based configuration for polling, models, logging mode, and optional cloud integrations.

## Architecture

OnCallAI follows a simple agent-inspired pipeline:

1. `runner` polls for incidents with `OPEN` status.
2. The collector stage retrieves context and logs for the incident.
3. The analyst stage evaluates evidence and drafts findings.
4. The supervisor stage writes the final report and marks the incident complete.
5. The UI reads the persisted data and displays incident state, steps, and outputs.

### Main Components

- [`app/runner.py`](app/runner.py): Main polling loop and incident execution flow.
- [`app/db/dal.py`](app/db/dal.py): Database access layer for incidents, steps, and reports.
- [`app/middleware/alert_normalizer.py`](app/middleware/alert_normalizer.py): CloudWatch-style alert normalization into the incident schema.
- [`app/middleware/alert_ingest.py`](app/middleware/alert_ingest.py): Ingestion path for normalized alerts.
- [`app/middleware/cloudwatch_boto.py`](app/middleware/cloudwatch_boto.py): Real CloudWatch polling and alarm-to-incident ingestion.
- [`app/agents/collector_agent.py`](app/agents/collector_agent.py): Log selection and retrieval logic.
- [`app/agents/analyst_agent.py`](app/agents/analyst_agent.py): Retrieval-assisted analysis and mitigation generation.
- [`app/agents/supervisor.py`](app/agents/supervisor.py): Report compilation and workflow completion.
- [`ui/streamlit_app.py`](ui/streamlit_app.py): Operator-facing incident dashboard.
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
├── tests/              # Lightweight unit and incident-flow tests
├── ui/                 # Streamlit application
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

This polls current alarms in the `ALARM` state, normalizes them, and routes them through the same ingestion and deduplication path as local alert payloads.

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
- The runner picks up incidents with `OPEN` status.
- The runner dispatches the incident through collector, analyst, and supervisor stages.
- The analyst combines rule-based matching with retrieved examples from the bundled incident corpus.
- Agent steps are written back to the database as the incident is processed.
- Reports are stored in structured JSON plus Markdown.
- The UI reads directly from the database and lets you inspect filters, alert metadata, timelines, payloads, and final reports.

This makes the project easy to demo, debug, and extend locally.

## Current Scope and Limitations

This repository is best understood as a strong prototype rather than a production-ready incident response platform.

- The default runner currently uses a simplified processing path.
- The analyst uses lightweight local retrieval rather than a full production retrieval pipeline or LLM-backed reasoning engine.
- CloudWatch polling currently focuses on ingesting active alarms; richer recovery handling and broader provider support can be extended further.
- Authentication, authorization, retries, and multi-tenant concerns are not implemented.
- The UI is optimized for local inspection and demos rather than operational scale.

## Extension Ideas

Good next steps for evolving OnCallAI include:

- Connect real alert providers such as CloudWatch, PagerDuty, or Opsgenie.
- Replace heuristic analysis with retrieval-backed or model-backed reasoning.
- Add incident enrichment from dashboards, deploy metadata, and service ownership data.
- Introduce alert deduplication and correlation across multiple signals.
- Add automated remediation suggestions with human approval gates.
- Expand the UI into a richer operations console with filtering and search.

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
