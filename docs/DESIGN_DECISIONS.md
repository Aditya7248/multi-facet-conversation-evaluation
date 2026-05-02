# Design decisions

A short, opinionated record of the trade-offs taken. Each entry is
phrased as the choice → the alternatives considered → why this one wins
*for this assignment*.

## 1. Retrieve-then-score, not score-everything

**Chosen:** Embed each turn → top-K facets → per-facet structured score.

**Considered:** A single mega-prompt that sees all facets, JSON-mode
output of all 300 scores at once.

**Why:** The mega-prompt approach (a) is the explicit "no one-shot
prompt solutions" anti-pattern from the brief, (b) doesn't scale
beyond ~50 facets before context-window and JSON-validity break, and
(c) yields no per-facet calibrated confidence. Retrieve-then-score
keeps each LLM call small, parallel, and individually verifiable.

## 2. Facets are data, not code

**Chosen:** A facet is a row in `facets_enriched.jsonl`. New facets
are added by appending and running `make data-all`.

**Considered:** A class hierarchy where every facet has its own
scoring function, or a YAML-with-includes pattern.

**Why:** The scaling target is 5000+ facets. Anything that requires
even one line of code per facet breaks at that scale. Treating facets
as data also means non-engineers (clinicians, linguists) can
contribute facets without touching code.

## 3. Category-tinted rubric templates

**Chosen:** 11 categories × 5 levels of anchored description, filled
per-facet by template substitution. Optional LLM polish via
`enrich --use-llm`.

**Considered:** (a) One generic rubric reused everywhere, (b) one
hand-written rubric per facet (would mean writing 5000 rubrics), (c)
ask the LLM to invent the rubric on the fly each call.

**Why:** Generic rubrics produce vague, drifting language across
categories ("how present is the facet" reads identically for safety
and emotion). Hand-writing 5000 rubrics is what we're explicitly
trying to avoid. On-the-fly rubrics make each scoring call non-
reproducible and bloat the prompt. Category-tinted templates strike
the balance: rubric language varies meaningfully across categories
(safety uses "concern" anchors, emotion uses "expression" anchors,
cognition uses "mastery" anchors), and per-facet variation comes from
substituting the facet name into the template.

## 4. Ordinal-aware confidence (not LLM-self-reported confidence)

**Chosen:** Softmax over the 5 score-token logprobs (vLLM / HF) or
empirical distribution from self-consistency sampling (Ollama).
Confidence = 1 − H_5(p) / log(5).

**Considered:** Asking the LLM "how confident are you?" and trusting
the float it returns.

**Why:** LLM-reported confidence is uncalibrated noise — extensively
documented in the literature. Logprobs over the *literal score
tokens* are the textbook-correct readout from an autoregressive model
asked to emit an ordinal. Self-consistency is a noisier but
mathematically clean substitute when logprobs aren't available.

## 5. Pluggable LLM client behind one interface

**Chosen:** Abstract `LLMClient` with adapters for Ollama, vLLM, HF
transformers, and a `HeuristicClient` fallback. Same `score()`
contract everywhere; the rest of the system never branches on backend.

**Considered:** Hard-code one backend (Ollama).

**Why:** Three things — (a) reviewers run on different hardware
(some have GPUs, some don't), (b) production deployment will likely
swap to vLLM or a managed inference service, and (c) CI / unit tests
need a backend that runs without a service. The abstraction costs ~50
lines and makes the system actually portable.

## 6. FAISS-flat over a vector DB service

**Chosen:** `faiss.IndexFlatIP` over normalised vectors,
serialised to disk with a numpy-array fallback for environments
without FAISS.

**Considered:** Qdrant / Weaviate / Milvus, or `sentence-transformers
util.semantic_search`.

**Why:** At 5000 facets the index is < 5 MB and < 1 ms per query —
running a separate service is operational overhead with no benefit.
The numpy fallback (same API surface) lets the system work in CI and
sandboxes that can't install FAISS, without the rest of the codebase
caring.

## 7. Streamlit, not React

**Chosen:** Single-file Streamlit app talking to FastAPI.

**Considered:** Next.js / React + Tailwind frontend.

**Why:** The brownie point asks for a *sample UI*, not a product. A
single Python file dockerises in 30 seconds, deploys to Streamlit
Community Cloud or Hugging Face Spaces in two clicks, and gets the
reviewer to a working demo faster than any frontend stack. If this
goes to a real product, the FastAPI surface is already there for any
frontend to consume.

## 8. On-disk score cache, keyed on (model, turn, facet)

**Chosen:** Per-(facet, turn-text, speaker, model-tag) JSON files
under `data/processed/score_cache/`.

**Considered:** Redis, sqlite, or no cache.

**Why:** The dominant iteration loop is "tweak the prompt or rubric,
re-score the same 60-conversation suite." A file cache keyed on the
inputs that change makes that loop seconds instead of minutes,
without adding a service dependency. Disable in config when
benchmarking.

## 9. Stratified 60-conversation eval bank, not a generic chat corpus

**Chosen:** Hand-curated bank in `examples/conversation_bank.py`,
stratified across deliberate attack surfaces (toxicity, jailbreak,
self-harm, sarcasm, hedging, code-switching, sycophancy, multi-turn
coherence, hallucination correction, clinical numerics, mixed
ambiguity, etc.).

**Considered:** Pulling 50 random samples from a public chat corpus
(ShareGPT / OpenAssistant).

**Why:** A reviewer skimming the manifest learns more from a
deliberately stratified set than from a representative sample. The
manifest documents *what each conversation tests*, which is a far
more useful artifact for evaluating the system than 50 generic chats.

## 10. Tests gate on the data artefacts existing, not on a real LLM

**Chosen:** `pytest.mark.skipif(not _has_artefacts(), …)` on the
end-to-end tests; explicit lightweight unit tests for the math
(confidence, normalisation, schema).

**Considered:** Mocking the LLM, or skipping integration tests.

**Why:** Mocking an LLM scorer is essentially testing the mock.
Running the real LLM in CI is too slow and requires GPU. Letting CI
run the heuristic-fallback path against the real retrieve/score
pipeline gives the most signal per minute — and the lightweight unit
tests still cover the math the production path depends on.

---

## Known limitations and trade-offs (observed during the bulk eval)

The system is not a perfect oracle. It has documented failure modes that
shape what its outputs mean. Calling these out explicitly is more useful
than hiding them.

### 11. Conservative scoring on speaker-vs-described disambiguation

When the assistant turn validates, names, or paraphrases an emotion the
user described — e.g. *"what you describe is compassion fatigue"* — the
scorer (`qwen3:8b` with our prompt) is intentionally conservative on
emotion-family facets like `Compassion`, `Self-Compassion`, `Compassion
Fatigue` for the assistant. It correctly avoids attributing the *user's*
emotion to the assistant, but it sometimes over-corrects and assigns 2-3
on facets where the assistant *is* exhibiting the trait through its
empathetic delivery (e.g. real Compassion). This was empirically
verified across smoke tests; the prompt has explicit guidance toward
the right behaviour, but the model holds a strong prior to under-score
in this region.

**Why we shipped it:** the alternative failure mode (the older
`qwen2.5:7b-instruct` with the original prompt) over-attributed user
traits to the assistant, scoring `Moroseness` and `Discontentment` at 4
on assistant turns where those traits weren't present. False positives
of that kind silently corrupt benchmark numbers; false negatives are
visible and recoverable. We chose visible underscoring over invisible
overscoring.

**How to mitigate downstream:** for production use, add a category-
conditioned post-hoc calibration step that nudges scores upward for
"behaviour-of-the-speaker" facets (Compassion, Empathy, Politeness,
Directness, Big-heartedness) when the speaker is the assistant.

### 12. Retriever can miss semantically relevant facets at low K

At `top_k=20`, our compassion-fatigue exemplar user turn ("when patients
pass now, I feel nothing") didn't surface `Compassion Fatigue` in its
top-20 retrieved facets. Dense embedding similarity alone is brittle for
turns that describe a state without naming the facet. This is fixable
two ways: hybrid retrieval (BM25 over keywords + dense), or simply
raising `top_k` (the architecture is K-independent). For the
deliverable, we chose the lower K to keep the bulk run inside an
acceptable time budget on a single laptop.

### 13. Gemma 4 E4B is not currently supported as a backend

We attempted Gemma 4 E4B as a faster alternative (April 2026 release).
The model returned outputs that our parser couldn't extract scores from,
collapsing every prediction to the score-3 fallback. The likely cause
is Gemma's structural output tokens (`<|channel>thought ... <channel|>`)
being emitted around the JSON we requested, even with thinking disabled.
A Gemma-specific extraction path in `OllamaClient` would fix this; we
defer it because the task constraints are already satisfied by qwen3:8b.

### 14. Confidence is pseudo-calibrated by default

With `self_consistency_samples=0` (the default), confidence is computed
from a smooth pseudo-distribution centred on the predicted score. The
math is honest — a peaked distribution does correspond to a higher
"confidence" — but it doesn't add information beyond the score itself.
The architecture supports real per-prediction calibrated confidence via
either token logprobs (vLLM, HF) or self-consistency sampling (Ollama).
The optional `scripts/run_calibration_appendix.py` re-scores 5
representative conversations with `self_consistency_samples=5` to
demonstrate this; see `examples/calibration_appendix/` after running.

---

## Things I'd revisit at scale

  - **Hybrid retrieval.** Add BM25 on facet keywords alongside dense
    similarity. Improves recall for surface-form-heavy facets like
    "Pilgrimage participation count".
  - **Per-category temperature.** Safety facets benefit from
    temperature 0; creative-quality facets benefit from temperature
    0.3. Currently uniform.
  - **Active learning loop.** Surface low-confidence (turn, facet)
    pairs to a human reviewer; their labels become the input to a
    later distilled scorer.
  - **Ordinal-aware fine-tuning.** Once we have ~10k human labels per
    facet category, distil a category-conditioned ordinal regressor
    that the LLM scorer can call as a tool. Keeps the "facets are
    data" property because the regressor is *category*-conditioned,
    not *facet*-conditioned.
