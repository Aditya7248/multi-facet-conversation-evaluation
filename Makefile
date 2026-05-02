.PHONY: help install install-hf clean lint test \
        data-clean data-enrich data-index data-all data-custom \
        run-api run-ui examples examples-zip report conv-table \
        docker-build docker-up docker-down

PY ?= python3
PIP ?= $(PY) -m pip

help:
	@echo "Targets:"
	@echo "  install          - install runtime deps"
	@echo "  install-hf       - install runtime + HuggingFace transformers backend"
	@echo "  data-clean       - normalize raw facets CSV"
	@echo "  data-enrich      - generate categories + 5-level rubrics"
	@echo "  data-index       - build FAISS facet-routing index"
	@echo "  data-all         - clean + enrich + index (uses data/raw/facets_raw.csv)"
	@echo "  data-custom CSV= - bring your own facets CSV (e.g. CSV=./my_facets.csv)"
	@echo "  run-api          - start FastAPI server (port 8080)"
	@echo "  run-ui           - start Streamlit UI (port 8501)"
	@echo "  examples         - generate + score 50+ stratified conversations"
	@echo "  report           - build examples/REPORT.md (aggregate Markdown digest)"
	@echo "  conv-table       - build examples/conversations_table.md (per-convo audit table)"
	@echo "  examples-zip     - zip the scored examples + report + table for the deliverable"
	@echo "  test             - run pytest"
	@echo "  lint             - run ruff"
	@echo "  docker-up        - docker compose up --build"
	@echo "  docker-down      - docker compose down"

install:
	$(PIP) install -r requirements.txt

install-hf:
	$(PIP) install -r requirements-hf.txt

lint:
	ruff check src tests

test:
	pytest

data-clean:
	$(PY) -m src.data_pipeline.clean

data-enrich:
	$(PY) -m src.data_pipeline.enrich

data-index:
	$(PY) -m src.data_pipeline.index

data-all: data-clean data-enrich data-index

# Bring your own facets CSV.
# Usage:  make data-custom CSV=/path/to/your_facets.csv
# Then restart the API (`make run-api`) to load the new facets.
data-custom:
	@if [ -z "$(CSV)" ]; then \
		echo "error: provide CSV=/path/to/your_facets.csv"; \
		echo "       expected format: one column, optional 'Facets' header, one facet name per row"; \
		exit 1; \
	fi
	@echo ">>> Using custom CSV: $(CSV)"
	$(PY) -m src.data_pipeline.clean --raw "$(CSV)"
	$(PY) -m src.data_pipeline.enrich
	$(PY) -m src.data_pipeline.index
	@echo ">>> Done. Restart the API (make run-api) to load the new facets."

run-api:
	$(PY) -m uvicorn src.api.server:app --host 0.0.0.0 --port 8080 --reload

run-ui:
	streamlit run src/ui/app.py --server.port 8501

examples:
	$(PY) -m examples.generate_conversations

examples-zip: examples report conv-table
	$(PY) scripts/zip_examples.py

report:
	$(PY) scripts/build_report.py

conv-table:
	$(PY) scripts/build_conversations_table.py

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down
