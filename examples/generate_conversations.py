"""Run the scoring pipeline against the 60-conversation bank.

Outputs (under ``examples/generated/``):
    {cid}.json                 full scored conversation, machine-readable
    manifest.csv               cid, title, tags, n_turns, avg_confidence, top facet
    summary.json               aggregate stats across the bank
    README.md                  human-readable intro to the ZIP

Then ``make examples-zip`` packages everything into
``examples/conversations_scored.zip`` for the assignment deliverable.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.scoring.pipeline import ScoringPipeline
from src.utils.config import REPO_ROOT
from src.utils.logging import get_logger
from src.utils.types import Conversation, ConversationTurn, Speaker

from examples.conversation_bank import CONVERSATIONS, get_tag_distribution

log = get_logger(__name__)

OUT_DIR = REPO_ROOT / "examples" / "generated"


def to_conversation(spec: dict) -> Conversation:
    turns = [
        ConversationTurn(turn_index=i, speaker=Speaker(spk), text=text)
        for i, (spk, text) in enumerate(spec["turns"])
    ]
    return Conversation(
        conversation_id=spec["cid"],
        title=spec["title"],
        tags=spec["tags"],
        turns=turns,
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pipeline = ScoringPipeline.default()

    manifest_rows: list[dict] = []
    aggregate = {
        "n_conversations": len(CONVERSATIONS),
        "tag_distribution": get_tag_distribution(),
        "backend": pipeline.client.name,
        "embedder": pipeline.retriever.meta.get("embedder"),
        "n_facets_indexed": pipeline.retriever.meta.get("n_facets"),
        "top_k": pipeline.top_k,
        "per_conversation": [],
    }

    for spec in CONVERSATIONS:
        conv = to_conversation(spec)
        result = pipeline.score_conversation(conv)
        out_path = OUT_DIR / f"{conv.conversation_id}.json"
        out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        # Top facet by mean score across turns
        top = result.summary.get("top_facets_by_mean_score") or [{}]
        top_facet_id = top[0].get("facet_id") if top else None

        manifest_rows.append({
            "cid": conv.conversation_id,
            "title": conv.title,
            "tags": "; ".join(conv.tags),
            "n_turns": len(conv.turns),
            "n_facet_scores": result.summary.get("n_facet_scores", 0),
            "avg_confidence": round(result.summary.get("avg_confidence", 0.0), 3),
            "top_facet_id": top_facet_id,
            "elapsed_seconds": result.pipeline_meta.get("elapsed_seconds"),
        })
        aggregate["per_conversation"].append(manifest_rows[-1])

    # Write manifest
    manifest_path = REPO_ROOT / "examples" / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary_path = REPO_ROOT / "examples" / "summary.json"
    summary_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")

    # README in the ZIP
    readme = (REPO_ROOT / "examples" / "README.md")
    readme.write_text(_render_readme(aggregate), encoding="utf-8")

    log.info("Scored %d conversations -> %s", len(CONVERSATIONS), OUT_DIR)
    log.info("Manifest: %s", manifest_path)
    log.info("Summary:  %s", summary_path)


def _render_readme(agg: dict) -> str:
    tags = "\n".join(f"- `{t}` × {n}" for t, n in agg["tag_distribution"].items())
    return f"""# Ocean Across — Scored Conversations Bank

This ZIP contains {agg['n_conversations']} conversations covering deliberate attack
surfaces of conversational evaluation, each scored end-to-end by the
Ocean Across pipeline.

## How they were scored

- **Backend:** `{agg['backend']}`
- **Embedder:** `{agg['embedder']}`
- **Facets indexed:** {agg['n_facets_indexed']}
- **Top-K facets per turn:** {agg['top_k']}

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

{tags}

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
"""


if __name__ == "__main__":
    main()
