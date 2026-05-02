# Ocean Across — Scored Conversations Bank

This ZIP contains 60 conversations covering deliberate attack
surfaces of conversational evaluation, each scored end-to-end by the
Ocean Across pipeline.

## How they were scored

- **Backend:** `ollama:qwen3:8b`
- **Embedder:** `sentence-transformers/all-MiniLM-L6-v2`
- **Facets indexed:** 399
- **Top-K facets per turn:** 20

The pipeline is documented in the parent repository's
`docs/ARCHITECTURE.md`. Each `*.json` file is a `ConversationScores`
artifact (Pydantic schema; see `src/utils/types.py`) and contains:

- the original conversation,
- the facets retrieved for each turn,
- per-facet score (1..5), confidence (0..1) and rationale,
- a per-conversation summary (top facets, low-confidence flags,
  category rollup),
- pipeline metadata so the run is reproducible.

## Stratification

Conversations are deliberately distributed across the major attack
surfaces of multi-facet conversation evaluation:

- `personality` × 11
- `emotion` × 9
- `cognition` × 8
- `safety` × 7
- `pragmatics` × 6
- `behavioral` × 6
- `clinical` × 5
- `relational` × 5
- `refusal` × 5
- `multi_turn` × 4
- `spirituality` × 4
- `mixed` × 4
- `coherence` × 2
- `linguistic_quality` × 2
- `toxicity` × 1
- `self-harm` × 1
- `jailbreak` × 1
- `bias` × 1
- `privacy` × 1
- `harm` × 1
- `joy` × 1
- `grief` × 1
- `compassion-fatigue` × 1
- `anger` × 1
- `fear` × 1
- `sarcasm` × 1
- `hedging` × 1
- `code-switching` × 1
- `politeness` × 1
- `irony` × 1
- `statistics` × 1
- `common-sense` × 1
- `numerical` × 1
- `anatomy` × 1
- `risktaking` × 1
- `naivety` × 1
- `honesty` × 1
- `submissiveness` × 1
- `passive-aggressive` × 1
- `overprotective` × 1
- `cunningness` × 1
- `kindness` × 1
- `sycophancy` × 1
- `factuality` × 1
- `symptom` × 1
- `numeric` × 1
- `lifestyle` × 1
- `diet` × 1
- `fitness` × 1
- `mindfulness` × 1
- `leadership` × 1
- `specialist` × 1
- `ambiguity` × 1
- `self-esteem` × 1
- `assistant_quality` × 1
- `verbosity` × 1
- `social-engineering` × 1
- `creativity` × 1

## Reproducing

From the repo root:

```bash
make data-all       # clean + enrich + index the facet catalogue
make examples       # rerun this scoring batch
make examples-zip   # zip into examples/conversations_scored.zip
```

To get higher-quality numbers, point the pipeline at a real LLM:

```bash
ollama pull qwen3:8b
LLM_BACKEND=ollama make examples
```
