# DevOps Incident Responder — Agentic AI (Hackathon MVP)

Autonomous, explainable incident triage for DevOps/SRE: watches alerts, retrieves context + logs, performs RAG-grounded analysis, and produces a concise RCA with mitigation suggestions — all visible in a simple live UI.

## ✨ Features (MVP)
- Alert intake: Poll (simulated) CloudWatch alerts via small middleware.
- Supervisor + Sub-agents (LangGraph): Collector + Analyst; Supervisor compiles report.
- RAG grounding: Chroma/FAISS over playbook snippets (error → cause → fix).
- Explainability: each agent step written to DB; UI streams thinking & actions.
- Report output: JSON + Markdown; downloadable from UI.
- Safety: read-only by default.

## 🧱 Tech Stack
Streamlit • LangGraph • Python • SQLite (default) or Postgres • Chroma/FAISS • OpenAI (optional) • boto3 (optional)

## 🚀 Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Seed toy data
python scripts/seed_rag_examples.py
python scripts/seed_logs.py
python scripts/seed_incidents.py

# (Optional) build RAG index
python app/rag/build_index.py

# Run agent loop
python app/runner.py

# Launch UI
streamlit run ui/streamlit_app.py
```

See more details in README for architecture and scripts.
