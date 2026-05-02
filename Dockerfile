## Multi-stage Dockerfile.
## Build target chosen by the docker-compose `target:` directive.

# ---------- Base ----------
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---------- Common app bits ----------
COPY pyproject.toml Makefile ./
COPY configs ./configs
COPY src ./src
COPY data ./data
COPY examples ./examples

# Pre-build the data artefacts at image build time so the container
# starts ready to serve. Reviewers can `make data-all` to refresh.
RUN PYTHONPATH=. python -m src.data_pipeline.clean \
 && PYTHONPATH=. python -m src.data_pipeline.enrich \
 && PYTHONPATH=. python -m src.data_pipeline.index

ENV PYTHONPATH=/app

# ---------- API ----------
FROM base AS api
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8080"]

# ---------- UI ----------
FROM base AS ui
EXPOSE 8501
ENV API_URL=http://api:8080
CMD ["streamlit", "run", "src/ui/app.py", \
     "--server.port", "8501", "--server.address", "0.0.0.0", \
     "--browser.gatherUsageStats", "false"]
