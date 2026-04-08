run:
	python app/runner.py

ui:
	streamlit run ui/streamlit_app.py

seed:
	python scripts/seed_rag_examples.py && \
	python scripts/seed_logs.py && \
	python scripts/seed_incidents.py

clean:
	rm -f dev.db && rm -rf app/reports/*
