PYTHON ?= python3

run:
	$(PYTHON) app/runner.py

ui:
	streamlit run ui/streamlit_app.py

seed:
	$(PYTHON) scripts/seed_rag_examples.py && \
	$(PYTHON) scripts/seed_logs.py && \
	$(PYTHON) scripts/seed_incidents.py

clean:
	rm -f dev.db && rm -rf app/reports/*
