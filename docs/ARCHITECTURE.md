# Architecture

This document explains the why behind the design. For the *what* (entry
points, scripts, endpoints), see the README.

## The shape of the problem

We need to score every conversational turn on hundreds — soon
thousands — of qualitative facets, on a 5-point ordinal scale, using an
open-weights ≤ 16B model. A naive solution ("ask an LLM to score all
facets at once") fails on three axes simultaneously:

  1. **Context window.** A single mega-prompt with 5000 facet
     definitions blows past any open-weights context limit.
  2. **Calibration.** A single response collapses 5000 ordinal calls
     into one autoregressive sample; per-facet confidence becomes
     impossible to extract.
  3. **Reliability.** Long structured outputs are brittle — one drifted
     comma rebreaks 4999 scores.

The right framing is to treat **facets as data, not code**, and route
each turn to only the *relevant* facets for actual scoring.

## Pipeline stages

```
RAW  ── clean ──► CLEANED ── enrich ──► ENRICHED (rubrics, categories)
                                              │
                                              ▼
                                          INDEX  (FAISS / numpy ANN)
                                              │
TURN ── embed ──► RETRIEVER (top-K) ──► SCORER (per-facet structured)
                                              │
                                              ▼
                                       TURN SCORES (with confidence)
```

### Stage 1 — Cleaning

`src/data_pipeline/clean.py` normalises the messy `Facets Assignment.csv`:

  - drops the literal header row "Facets",
  - strips numbered prefixes ("793. Sufi practice...", common when CSVs
    are pasted from PDFs),
  - removes trailing punctuation (`Democratic Leadership:` →
    `Democratic Leadership`),
  - splits CamelCase (`HonestyHumility` → `Honesty Humility`),
  - de-duplicates case-insensitively,
  - emits a stable `facet_id` slug for every row.

This module is intentionally LLM-free so it runs in any environment.
Output: `data/processed/facets_cleaned.csv`.

### Stage 2 — Enrichment

`src/data_pipeline/enrich.py` adds the structure scoring depends on.
For every cleaned facet:

  - **Category** — one of 11 (linguistic_quality, pragmatics, safety,
    emotion, personality, cognition_reasoning, relational,
    clinical_health, behavioral_lifestyle, spirituality_culture, other).
    Computed by a two-step procedure: a high-precision keyword
    fast-path, then an embedding argmax against per-category seed
    text. Falls through to `other` only when both fail.
  - **Description** — a one-paragraph definition that grounds the LLM
    scorer.
  - **Rubric** — five anchored levels (1..5) generated from
    category-tinted templates in `rubric_templates.py`. Safety facets
    use "no concern .. severe concern" anchors; emotion uses "opposite
    affect .. intense expression"; cognition uses "no reasoning ..
    expert"; etc. Anchors per category make rubric language *vary by
    facet* without writing 399 rubrics by hand. The optional
    `--use-llm` flag refines these via the configured LLM client when a
    real model is reachable.
  - **Score scale** — `[1, 2, 3, 4, 5]` by default, configurable.
  - **Score direction** — positive (more = more), negative, or bipolar.
  - **Applicable speaker** — user / assistant / both.
  - **Keywords** — tokens that the heuristic fallback uses for
    keyword-overlap scoring; also useful for hybrid retrieval.

Output: `data/processed/facets_enriched.{csv,jsonl}`.

The CSV is human-friendly (one row per facet, anchor descriptions in
columns); the JSONL is the canonical artefact downstream code reads.

### Stage 3 — Indexing

`src/data_pipeline/index.py` embeds each facet's `embed_text()`
(name + category + description + rubric + keywords) and builds a FAISS
`IndexFlatIP` over L2-normalised vectors (cosine similarity).

For < 100k facets this is sub-millisecond per query; the swap to HNSW
or IVF is a one-line change. The numpy fallback (`VectorIndex`) is
identical in API and used in environments without FAISS.

Output: `data/index/facets.{faiss,npy,kind}` + `facets_meta.json`.

### Stage 4 — Retrieval

`src/scoring/retriever.py` is the lever that lets the architecture
scale to 5000+ facets without redesign. At inference time the
retriever:

  1. embeds the turn text with the same encoder used in stage 3,
  2. runs top-K cosine similarity over the index,
  3. optionally filters by category (with a 4× over-fetch to preserve
     recall after the filter),
  4. returns `RetrievedFacet` records with similarity, rank, and the
     full enriched facet definition.

K is a config knob. The reviewer can set it to 5, 40, 200 — the LLM
budget per turn is then 5, 40, 200 small prompts. Whether the
catalogue is 300 or 5000 facets, K stays constant.

### Stage 5 — Scoring

`src/scoring/scorer.py` builds a tightly-scoped prompt for each
retrieved facet:

```
SYSTEM: meticulous-evaluator persona, JSON-only output, 5-class rubric usage rules
USER:   facet name, category, description, anchored 5-level rubric, conversation
        context (most recent first), the turn to score
        ───
        Respond with: {"score": int, "rationale": str ≤30 words, "evidence_span": str}
```

Per-facet scoring inside a turn runs in a `ThreadPoolExecutor` (config:
`scoring.parallel_workers`). The on-disk `ScoreCache` keys on
`(model_tag, facet_id, turn_speaker, turn_text)` so re-runs are fast
during prompt iteration.

### Stage 6 — Confidence

The scorer returns `score_distribution` — a 5-element softmax over the
ordinal classes — and `confidence`:

```
confidence = 1 − H_5(p) / log(5)
```

How `score_distribution` gets populated depends on the backend:

  - **vLLM / HF.** Read the per-token logprobs at the score-token
    position. Softmax the logprobs of the digit tokens "1".."5". This
    is the principled, calibrated approach.
  - **Ollama.** Token logprobs aren't reliably exposed. We use
    self-consistency instead: *N* independent generations at temp 0.7,
    empirical distribution of returned scores. Resolution = 1/N.
  - **Heuristic / fallback.** A smooth ordinal pseudo-distribution
    centred on the predicted score. Used only when no real LLM is
    reachable; explicitly flagged in logs.

### Stage 7 — Orchestration

`src/scoring/pipeline.py` composes retriever + scorer, exposes
`ScoringPipeline.score_conversation(...)`, and computes a per-turn
summary (top facets, low-confidence flags, category-level rollup,
pipeline metadata). The same orchestrator drives:

  - the FastAPI service (`src/api/server.py`),
  - the Streamlit UI (`src/ui/app.py`),
  - the 60-conversation eval generator (`examples/generate_conversations.py`).

## How this scales to 5000 facets

| Concern | Why it stays constant |
| --- | --- |
| LLM cost per turn | We score top-K (default 40), not all facets. |
| Context window | Each LLM call sees one rubric + one turn, ~700 tokens. |
| Index latency | FlatIP < 1 ms at 5k facets; HNSW < 5 ms at 50k. Swap-in trivial. |
| Memory | 5k × 384-d float32 ≈ 8 MB. Trivial. |
| Onboarding new facets | Append to CSV → `make data-all`. No retraining. |
| Calibrating confidence | Per-facet, per-turn — independent of catalogue size. |

The only parameter that actually scales with the catalogue is **build
time** of the FAISS index, which is once-per-catalogue-update and
fast (sentence-transformers can embed 5k 200-token strings in < 30 s on
CPU).

## What's deliberately *not* here

  - **Fine-tuning a scorer.** Per-facet calibrated rubric prompting is
    strictly cheaper than fine-tuning across hundreds of facets, and
    it preserves the "facets are data" property. Fine-tuning would
    break it.
  - **A vector DB service.** FAISS-flat in-memory is enough at this
    scale; running Qdrant/Weaviate would add ops surface for no gain.
  - **An ordinal regression head.** Tempting, but it would require
    labelled training data per facet — incompatible with the goal of
    onboarding new facets without retraining.
