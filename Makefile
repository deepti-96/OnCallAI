PYTHON ?= python3

.PHONY: run test simulate-alert poll-cloudwatch seed clean mind-demo mind-demo-live mind-test console

run:
	$(PYTHON) app/runner.py

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

mind-test:
	$(PYTHON) -m unittest tests.test_mind_memory -v

mind-demo:
	$(PYTHON) scripts/mind_demo.py

mind-demo-live:
	$(PYTHON) scripts/mind_demo.py --live

console:
	$(PYTHON) -m app.web.server --simulate-mind
