"""Calibration appendix — re-score 5 representative conversations with
self_consistency_samples=5 to produce REAL per-prediction confidence variance.

This complements the bulk eval (which runs with self_consistency_samples=0 for
speed and ships uniform pseudo-confidence). The appendix demonstrates that the
architecture supports calibrated ordinal confidence — flip one config knob and
every prediction gets a genuine empirical 5-class distribution.

Selected conversations cover five distinct attack surfaces:

    ec02 — self-harm escalation (safety + emotion + multi-turn)
    ec09 — compassion fatigue (the canonical inference test)
    ec33 — sycophantic over-agreement (refusal + factuality)
    ec36 — hallucination correction (multi-turn factuality)
    ec55 — low-effort assistant reply (linguistic quality)

Run:
    PYTHONPATH=. python scripts/run_calibration_appendix.py

Outputs:
    examples/calibration_appendix/<cid>.json     full ConversationScores
    examples/calibration_appendix/summary.json   meta about the appendix
    examples/calibration_appendix/README.md      what's in here, why it's here

Cost: 5 conversations × ~2.5 turns × 15 facets × (1 + 5 self-consistency)
      ≈ 1100 LLM calls @ ~4.5s each ≈ 80 minutes on a Mac.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.models.llm_client import OllamaClient
from src.scoring.pipeline import ScoringPipeline
from src.scoring.retriever import build_default_retriever
from src.utils.config import REPO_ROOT, load_config
from src.utils.logging import get_logger
from src.utils.types import Conversation, ConversationTurn, Speaker

from examples.conversation_bank import CONVERSATIONS

log = get_logger(__name__)


APPENDIX_CIDS = ["ec02", "ec09", "ec33", "ec36", "ec55"]
N_SAMPLES = 5
TOP_K = 15

OUT_DIR = REPO_ROOT / "examples" / "calibration_appendix"


_README = """# Calibration Appendix

This folder ships **five** conversations re-scored with
`self_consistency_samples = {n}` so every per-facet score has a real,
empirical confidence distribution.

The bulk eval in `examples/conversations_scored.zip` was produced with
`self_consistency_samples = 0` for speed. That means the bulk run ships
uniform pseudo-confidence — calibrated by construction (peak on the
predicted score) but not informative per prediction. This appendix
proves out the *real* confidence path: the architecture supports it,
flipping one config flag activates it, and at scale it can be re-run on
every prediction once GPU budget allows.

## Conversations

| cid | attack surface |
| --- | --- |
| ec02 | self-harm escalation — safety + emotion + multi-turn |
| ec09 | compassion fatigue — canonical inference test |
| ec33 | sycophantic over-agreement — refusal + factuality |
| ec36 | hallucination correction — multi-turn factuality |
| ec55 | low-effort assistant reply — linguistic quality |

## Method

For each (turn, facet) pair we run the scorer **N+1** times — one greedy
pass at temperature 0 plus N samples at temperature 0.7. The empirical
distribution of returned scores becomes `score_distribution`, and
`confidence = 1 − H₅(p) / log 5`.

When N ≥ 5 the distribution has 6 distinct shape buckets, which is
enough resolution for the entropy-based confidence to actually move
across predictions. Compare the spread in this appendix against the
uniform 0.54 numbers in the bulk JSON to see the difference.

## Reproducing

```bash
ollama serve
PYTHONPATH=. python scripts/run_calibration_appendix.py
```
""".format(n=N_SAMPLES)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    retriever = build_default_retriever()
    client = OllamaClient(
        host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        model=cfg["llm"]["model"],
        self_consistency_samples=N_SAMPLES,
    )
    pipe = ScoringPipeline(
        retriever=retriever,
        client=client,
        top_k=TOP_K,
        parallel_workers=2,
    )

    selected = [c for c in CONVERSATIONS if c["cid"] in APPENDIX_CIDS]
    if len(selected) != len(APPENDIX_CIDS):
        missing = set(APPENDIX_CIDS) - {c["cid"] for c in selected}
        raise RuntimeError(f"Calibration appendix missing CIDs: {missing}")

    log.info(
        "Calibration appendix: %d conversations × top_k=%d × self_consistency=%d",
        len(selected), TOP_K, N_SAMPLES,
    )

    appendix_summary: list[dict] = []
    for spec in selected:
        turns = [
            ConversationTurn(turn_index=i, speaker=Speaker(s), text=t)
            for i, (s, t) in enumerate(spec["turns"])
        ]
        conv = Conversation(
            conversation_id=spec["cid"],
            title=spec["title"],
            tags=spec["tags"],
            turns=turns,
        )
        result = pipe.score_conversation(conv)
        out_path = OUT_DIR / f"{conv.conversation_id}.json"
        out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        confidences = [s.confidence for ts in result.turn_scores for s in ts.scores]
        appendix_summary.append({
            "cid": conv.conversation_id,
            "title": conv.title,
            "n_scores": len(confidences),
            "confidence_min": round(min(confidences, default=0.0), 3),
            "confidence_max": round(max(confidences, default=0.0), 3),
            "confidence_mean": round(sum(confidences) / max(1, len(confidences)), 3),
            "elapsed_seconds": result.pipeline_meta.get("elapsed_seconds"),
        })
        log.info("  ✓ wrote %s  (mean conf %.2f)", out_path.name, appendix_summary[-1]["confidence_mean"])

    (OUT_DIR / "summary.json").write_text(
        json.dumps({
            "n_conversations": len(selected),
            "top_k": TOP_K,
            "self_consistency_samples": N_SAMPLES,
            "selected_cids": APPENDIX_CIDS,
            "per_conversation": appendix_summary,
        }, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "README.md").write_text(_README, encoding="utf-8")
    log.info("Calibration appendix complete -> %s", OUT_DIR)


if __name__ == "__main__":
    main()
