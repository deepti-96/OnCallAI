PYTHON ?= python3

.PHONY: run ui test simulate-alert poll-cloudwatch seed clean

run:
	$(PYTHON) app/runner.py

ui:
	$(PYTHON) -m streamlit run ui/streamlit_app.py

test:
	$(PYTHON) -m unittest discover -s tests

simulate-alert:
	$(PYTHON) app/middleware/cloudwatch_simulator.py

poll-cloudwatch:
	$(PYTHON) app/middleware/cloudwatch_boto.py

seed:
	$(PYTHON) scripts/seed_rag_examples.py && \
	$(PYTHON) scripts/seed_logs.py && \
	$(PYTHON) scripts/seed_incidents.py

clean:
	rm -f dev.db && rm -rf app/reports/*
