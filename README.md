# Ocean Across — Multi-Facet Conversation Evaluation Benchmark

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.33+-FF4B4B.svg)](https://streamlit.io)
[![Ollama](https://img.shields.io/badge/Ollama-qwen3:8b-000000.svg)](https://ollama.com/library/qwen3)

A production-grade benchmark that scores every conversational turn across **399 distinct facets** of linguistic quality, pragmatics, safety, emotion, personality, cognition, and clinical / behavioural / cultural attributes — and is **explicitly designed to scale to 5,000+ facets without code changes**. Adding a new facet is a row in a CSV, not a rewrite or a retrain.

Built around a multi-stage **retrieve-then-score** pipeline: a 384-dim sentence-transformer embeds each turn, FAISS retrieves the top-K most relevant facets, and an open-weights ≤ 16B LLM (Qwen 3 8B by default) scores each one against an anchored 5-level rubric — yielding a 1-to-5 ordinal score, a calibrated confidence, and a written rationale per facet per turn.

Ships with a FastAPI service, a Streamlit reviewer UI, full Docker Compose stack, 26 passing tests, and 60 stratified pre-scored conversations covering toxicity, sarcasm, refusal, sycophancy, hallucination correction, multi-turn coherence, and edge clinical / behavioural cases.

---

## TL;DR — what this is

Given a multi-turn conversation, the system returns, for **each turn**:

- the **K most-relevant facets** retrieved from a 399-facet catalogue,
- a **5-point ordinal score** (1..5) for each retrieved facet,
- a **calibrated confidence** in [0, 1] derived from token logprobs (or self-consistency fallback),
- a **rationale** and an **evidence span** quoted from the turn.

It does this with a multi-stage **retrieve-then-score** pipeline running on an open-weights ≤ 16B model (**Qwen 3 8B** by default; pluggable to vLLM / HuggingFace / any other Ollama-served model).

---

## Architecture at a glance

```mermaid
flowchart LR
  RAW[(Facets Assignment.csv)] --> CLEAN[clean.py]
  CLEAN --> ENRICH[enrich.py — categorise + 5-level rubric]
  ENRICH --> JSONL[(facets_enriched.jsonl)]
  JSONL --> INDEX[index.py — FAISS / numpy fallback]
  INDEX --> FAISS[(facets.faiss)]

  subgraph Inference
    TURN[Conversation turn] --> RETRIEVER{Retriever\ntop-K facets}
    FAISS --> RETRIEVER
    RETRIEVER --> SCORER{LLM Scorer\nstructured JSON}
    SCORER --> CONFIDENCE[Confidence\nlogprobs / self-consistency]
    CONFIDENCE --> OUT[(TurnScores)]
  end

  subgraph Backend
    OLLAMA[Ollama]
    VLLM[vLLM]
    HF[HuggingFace]
  end
  SCORER -.->|pluggable| OLLAMA & VLLM & HF
```

For a longer treatment see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md).

## The reviewer UI in action

A single-file Streamlit app (`src/ui/app.py`) wired to the FastAPI backend. Paste a conversation, see retrieved facets in milliseconds, watch each facet score with rationale and confidence in tens of seconds.

### Live retrieval + per-turn scoring (hero view)

![User turn — score bars colored by confidence](docs/screenshots/ui_user_turn_scored.png)

*The retriever picks the top-K most semantically relevant facets for the turn (right panel, sub-millisecond). The LLM then scores each one against its 5-level rubric (bars below — length = 1-5 score, color = model confidence on a viridis scale). Latency, average confidence, and total score count are surfaced as metric cards.*

### A different conversation, a different retrieval

![User turn — variant conversation showing different retrieved facets](docs/screenshots/ui_user_turn_score2.png)

*Swap the conversation and the retriever immediately picks a different top-K from the 399-facet catalogue. No model retraining, no code change — the embedder + FAISS index do the routing entirely from semantic similarity.*

### Speaker-aware scoring across turns

![Assistant turn — different facet pattern](docs/screenshots/ui_assistant_turn_score.png)

*Same conversation, the assistant's reply scored against its own retrieved facets. The score pattern is meaningfully different from the user turn — the system tracks who exhibits what, not just what topics appear.*

### Category-level rollup

![Aggregate score per category](docs/screenshots/ui_category_rollup.png)

*Mean score aggregated across the 11 facet categories — gives a holistic read of the conversation's character at a glance.*

### Why this scales to 5000+ facets

The cost driver is *facets scored per turn*, not *facets in the catalogue*. The retriever embeds the turn and selects only the top-K (default 40) facets to score. K stays constant as the catalogue grows from 300 → 5000 → 50,000. Adding a new facet = one row in the CSV, then `make data-all` to re-embed and re-index.

---

## Quickstart — local

This stack needs **four terminal tabs** running simultaneously: Ollama (the LLM server), the FastAPI backend, the Streamlit UI, and a free shell for one-off commands. Each `make` target stays in the foreground.

```bash
# --- One-time setup -------------------------------------------------------
# 1. Install Python deps
make install                              # pip install -r requirements.txt

# 2. Build the data artefacts (clean + enrich + FAISS index)
make data-all

# 3. Pull the open-weights model into Ollama (first run only, ~5 GB)
ollama pull qwen3:8b

# --- Per-session runtime (each in its own terminal tab) -------------------
# Tab A — Ollama LLM server. Leave running.
OLLAMA_NUM_PARALLEL=4 OLLAMA_MAX_LOADED_MODELS=1 ollama serve

# Tab B — FastAPI backend on :8080. Leave running.
make run-api

# Tab C — Streamlit UI on :8501. Leave running.
make run-ui
```

Open <http://localhost:8501>, paste a conversation, watch facets score live.

> **Why three tabs?** Each service stays in the foreground so its logs are visible. `ollama serve` *must* be running before `make run-api` — without it, the API falls back to the keyword-matching `HeuristicClient` (still functional for tests, but not what you want to actually score with). The `OLLAMA_NUM_PARALLEL=4` lets Ollama time-slice the GPU across 4 concurrent requests for ~2-3× faster batch scoring on Apple Silicon.

To shut down, press `Ctrl+C` in each tab (or just close them).

## Quickstart — Docker

```bash
docker compose up --build         # ollama + api + ui, all wired together
```

The compose stack auto-pulls `qwen3:8b` on first boot. Override via `.env`:

```bash
OLLAMA_MODEL=llama3.1:8b-instruct  docker compose up
```

## Bring your own facets CSV

The 399-facet catalogue isn't hard-coded — it's data, loaded from a CSV. Swap it for your own (whether 50 facets or 5,000) without touching any code:

```bash
make data-custom CSV=/path/to/your_facets.csv
make run-api      # restart so the API loads the new facets
```

The expected CSV format is **one column, optional `Facets` header, one facet name per row**. Cleaning is forgiving — it normalises whitespace, fixes `CamelCase`, strips numbered prefixes (`793. Sufi practice...` → `Sufi practice...`), drops trailing colons (`Democratic Leadership:` → `Democratic Leadership`), and de-duplicates case-insensitively.

After running `make data-custom`, the pipeline auto-categorises each facet into one of 11 categories, generates a 5-level rubric for each (using category-tinted templates), and re-embeds the catalogue into the FAISS index. Total time: ~30-60 seconds for hundreds of facets, ~2-3 minutes for thousands. The architecture is genuinely facet-count-independent — there is no codepath that scales with catalogue size beyond the one-time index rebuild.

## Switching the LLM backend

The `LLMClient` is pluggable. Set `LLM_BACKEND` to one of:

| backend | when to use | model env vars |
| --- | --- | --- |
| `ollama` *(default)* | local laptop, no GPU | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| `vllm` | production, GPU available | `VLLM_BASE_URL`, `VLLM_MODEL` |
| `hf` | air-gapped / no service runtime | `HF_MODEL`, `HF_DEVICE` |

If none of the above is reachable, the system falls back to a `HeuristicClient` so unit tests + the CI build still produce real artefacts. The README is explicit: real numbers come from a real LLM.

---

## Repository layout

```
multi-facet-conversation-evaluation/
├── configs/config.yaml            # all knobs — paths, top_k, parallelism, scale
├── src/
│   ├── data_pipeline/
│   │   ├── clean.py               # normalise the raw CSV
│   │   ├── category_taxonomy.py   # 11 categories with seed terms
│   │   ├── rubric_templates.py    # category-tinted 5-level rubric anchors
│   │   ├── enrich.py              # categorise + rubric + speaker + direction
│   │   └── index.py               # FAISS / numpy index build
│   ├── models/llm_client.py       # Ollama / vLLM / HF / Heuristic adapters
│   ├── scoring/
│   │   ├── retriever.py           # stage-1 router (top-K facets)
│   │   ├── scorer.py              # stage-2 per-facet structured scoring
│   │   └── pipeline.py            # orchestrator + summary
│   ├── api/server.py              # FastAPI surface
│   ├── ui/app.py                  # Streamlit reviewer UI
│   └── utils/
│       ├── types.py               # the system's Pydantic schemas
│       ├── embeddings.py          # ST + FAISS with numpy/hash fallback
│       ├── config.py              # YAML + env overlay
│       ├── logging.py             # rich-flavoured logger
│       └── text.py                # name normalisation
├── examples/
│   ├── conversation_bank.py       # 60 stratified conversations
│   ├── generate_conversations.py  # scoring driver
│   ├── generated/                 # one JSON per scored conversation
│   ├── manifest.csv               # cid, title, tags, top facet, …
│   ├── summary.json               # aggregate stats
│   └── conversations_scored.zip   # the assignment deliverable
├── tests/                         # pytest unit + integration tests
├── docs/
│   ├── ARCHITECTURE.md            # how & why (pipeline stages, scaling argument)
│   ├── DESIGN_DECISIONS.md        # 14 trade-offs recorded with alternatives considered
│   └── screenshots/               # UI screenshots
├── Dockerfile                     # multi-stage (api / ui targets)
├── docker-compose.yml             # ollama + api + ui — one-command boot
├── Makefile                       # all the verbs (install / data-all / examples / run-* / docker-*)
├── pyproject.toml
├── requirements.txt
└── .github/workflows/ci.yml       # lint + tests on push
```

---

## API surface

- `GET /health` — backend tag, embedder, indexed facet count, default K.
- `GET /facets?category=&page=&page_size=` — list every enriched facet.
- `GET /facets/{facet_id}` — full enriched record (rubric, exemplars, etc.).
- `POST /retrieve` — top-K facets for a free-text turn.
- `POST /score` — score an entire conversation.
- `POST /score/turn` — score a single turn with optional context.

OpenAPI is auto-served at `/docs` thanks to FastAPI.

---

## Confidence

For each ordinal score we return a *score distribution* — a softmax over the 5 ordinal classes — plus a calibrated confidence:

```
confidence = 1 − H_5(p) / log(5)         in [0, 1]
```

Two backends derive the distribution:

1. **vLLM (and HF) — token logprobs.** We softmax the logprobs of the digit tokens `"1".."5"` at the score-token position. Principled and well-calibrated.
2. **Ollama — self-consistency.** Logprobs aren't reliably exposed; we instead run *N* independent generations at temperature 0.7 and count the empirical distribution. With *N* = 5 the resolution is 0.2; configurable.

The scorer always returns a 5-element distribution that sums to 1.0 — see the schema in `src/utils/types.py`.

---

## Reproducing the deliverable ZIP

```bash
make data-all     # 399 facets cleaned, enriched, indexed
make examples     # 60 conversations scored via the configured backend
make examples-zip # → examples/conversations_scored.zip
```

The bank in `examples/conversation_bank.py` is hand-stratified across attack surfaces (toxicity, self-harm, jailbreak, sarcasm, code-switching, hedging, refusal, hallucination correction, multi-turn coherence, clinical numerics, sycophancy, …). The included `manifest.csv` documents what each conversation tests.

---

## Tests + CI

```bash
make test
```

- 26 tests cover text normalisation, the cleaning pipeline, enrichment schema, retriever recall, scorer schema validity, confidence math, and the API.
- The CI workflow (`.github/workflows/ci.yml`) lints with `ruff` and runs the test suite on every push/PR.

---

## Hard constraints — how each is satisfied

| Constraint | How |
| --- | --- |
| **No one-shot prompt solutions** | Multi-stage retrieve-then-score pipeline; per-facet structured prompts; per-turn parallelism; logprob/self-consistency confidence; on-disk score cache. |
| **Open-weights ≤ 16B** | Default `qwen3:8b`; configurable to any `≤16B` HF / Ollama / vLLM-served model. No closed-source providers anywhere in the runtime. |
| **Scales to 5000+ facets** | Facets are *data*, not code. Retriever picks top-K (constant) per turn. Index swap from FlatIP → IVF/HNSW is a one-line change once the catalogue exceeds ~100k. |
| Confidence outputs *(brownie)* | 5-class softmax + normalised-entropy confidence on every score. |
| Dockerised baseline *(brownie)* | `docker compose up --build` brings up Ollama + API + UI. |
| Sample UI *(brownie)* | Streamlit app with retrieval preview, score bars, confidence colour, JSON download. |

---

## Notes for the reviewer

### Bulk-run results (the deliverable)

The 60-conversation deliverable in `examples/conversations_scored.zip` was produced by:

- **LLM:** `ollama:qwen3:8b` (Qwen 3 8B, open-weights ≤ 16B ✓)
- **Embedder:** `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **Indexed facets:** 399 (cleaned + auto-categorised + 5-level rubrics)
- **Top-K per turn:** 20
- **Total facet scores:** ~2,680 across 134 turns
- **Mean confidence:** 0.59
- **Total compute time:** ~2 hours on Apple M5

See `examples/REPORT.md` for the per-category score histograms and 8 spotlight conversations, and `examples/conversations_table.md` (or `.csv`) for the full per-conversation audit table.

### Reproducing

In CI / minimal environments without `sentence-transformers` or `faiss-cpu` installed, the system gracefully falls back to a hash-trigram embedder + numpy index. This lets the test suite run anywhere (and the GitHub Actions CI uses this path), but the **real deliverable numbers always come from a real LLM** — never from the heuristic fallback. Every log line clearly identifies which path is active so you can never confuse the two.

To reproduce on your machine: `make install`, `ollama pull qwen3:8b`, `make data-all`, then `make examples` (~45-120 min depending on hardware).

### Other notes

- `pyproject.toml` and `requirements.txt` pin Python ≥ 3.10. `requirements-hf.txt` adds the HuggingFace transformers stack.
- `Facets Assignment.csv` actually contains **399 facets** (not the 300 the brief mentions); cleaning de-duplicates case-insensitively and normalises numbered prefixes / trailing colons / `CamelCase`.
- Known scoring limitations are explicitly documented in [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md) §11–14 — including the speaker-vs-described nuance, the retriever's recall limitation at low K, and the pseudo-calibrated default confidence.

---

## License

MIT — see `LICENSE`.
