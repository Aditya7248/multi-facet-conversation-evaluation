"""Side-by-side smoke test for an alternative LLM, without touching the main config.

Used to compare a different model against whatever the main pipeline is
currently configured for. Defaults to gemma4:e4b; override with SMOKE_MODEL.

Usage:
    PYTHONPATH=. python scripts/smoke_test_alt_model.py                       # gemma4:e4b
    PYTHONPATH=. SMOKE_MODEL=qwen3:14b python scripts/smoke_test_alt_model.py
    PYTHONPATH=. SMOKE_MODEL=gemma4:e2b python scripts/smoke_test_alt_model.py

Prereq:
    ollama pull <whatever model you want to test>     # only needed once per model

NOTE on running while a bulk eval is in progress:
    If your Ollama is started with OLLAMA_MAX_LOADED_MODELS=1 (the default we
    used earlier) and the bulk run is on a different model, this script will
    trigger a model swap that briefly slows the bulk eval. Three options:
      (a) run this AFTER the bulk run finishes — cleanest;
      (b) restart Ollama with MAX_LOADED_MODELS=2 to keep both resident:
          OLLAMA_NUM_PARALLEL=4 OLLAMA_MAX_LOADED_MODELS=2 ollama serve
      (c) just run it — Ollama swaps in ~5-15 s, you lose maybe one minute
          on the bulk run; usually fine.
"""

from __future__ import annotations

import os
import sys

from src.models.llm_client import OllamaClient
from src.scoring.pipeline import ScoringPipeline
from src.scoring.retriever import build_default_retriever
from src.utils.types import Conversation, ConversationTurn, Speaker


MODEL = os.environ.get("SMOKE_MODEL", "gemma4:e4b")
TOP_K = int(os.environ.get("SMOKE_TOP_K", "20"))


# Same canonical conversation as scripts/smoke_test.py — apples-to-apples.
CONV = Conversation(
    conversation_id=f"smoke-alt-{MODEL.replace(':', '-').replace('/', '-')}",
    title="Burnout disclosure (alt-model comparison)",
    tags=["emotion", "compassion-fatigue"],
    turns=[
        ConversationTurn(
            turn_index=0,
            speaker=Speaker.USER,
            text=(
                "I've been an oncology nurse for 15 years. When patients pass now, "
                "I just feel nothing. I think I'm a fraud."
            ),
        ),
        ConversationTurn(
            turn_index=1,
            speaker=Speaker.ASSISTANT,
            text=(
                "What you describe is a textbook presentation of compassion fatigue. "
                "It's not a character flaw — it's a documented occupational injury "
                "after sustained loss."
            ),
        ),
    ],
)


def _model_is_available(client: OllamaClient) -> bool:
    """Verify the model is actually pulled into this Ollama instance."""
    try:
        import httpx

        r = httpx.get(f"{client.host}/api/tags", timeout=5.0)
        r.raise_for_status()
        tags = [m["name"] for m in r.json().get("models", [])]
        if MODEL in tags or any(t.startswith(MODEL + ":") for t in tags):
            return True
        # Some Ollama versions report tags without the suffix
        bare = MODEL.split(":")[0]
        return any(t.startswith(bare + ":") or t == bare for t in tags)
    except Exception:
        return True   # Don't block on a malformed /api/tags; let scoring surface the real error.


def main() -> int:
    print(f"Smoke-testing alternative model: {MODEL}  (top_k={TOP_K})")
    print("  • Does NOT touch configs/config.yaml")
    print("  • Bypasses the score cache for clean comparison")
    print()

    client = OllamaClient(
        host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        model=MODEL,
        self_consistency_samples=0,
    )

    if not client.health():
        print(f"ERROR: Ollama not reachable at {client.host}.")
        print("       Make sure 'ollama serve' is running in another terminal.")
        return 2

    if not _model_is_available(client):
        print(f"ERROR: model '{MODEL}' isn't pulled into this Ollama instance.")
        print(f"       Run:   ollama pull {MODEL}")
        return 3

    retriever = build_default_retriever()
    pipe = ScoringPipeline(
        retriever=retriever,
        client=client,
        top_k=TOP_K,
        parallel_workers=2,            # smaller — don't fight the bulk run
        cache=None,                    # bypass cache for clean comparison
    )

    try:
        res = pipe.score_conversation(CONV, top_k=TOP_K)
    except Exception as e:
        print(f"ERROR: scoring failed — {e!r}")
        return 4

    print("=" * 78)
    print(f"Backend:   {res.pipeline_meta['client']}")
    print(f"Embedder:  {res.pipeline_meta['embedder']}")
    print(f"Latency:   {res.pipeline_meta['elapsed_seconds']:.1f}s")
    print("=" * 78)

    all_scores = [s.score for t in res.turn_scores for s in t.scores]
    print(
        f"Score spread: min={min(all_scores)}  max={max(all_scores)}  "
        f"unique={sorted(set(all_scores))}"
    )

    for t in res.turn_scores:
        print(f"\nTurn {t.turn_index} [{t.speaker.value}]:")
        print(" ", t.text[:90] + ("..." if len(t.text) > 90 else ""))
        for s in sorted(t.scores, key=lambda x: -x.score)[:8]:
            print(f"    {s.facet_name[:40]:40s}  score={s.score}  conf={s.confidence:.2f}")
            if s.rationale:
                print(f"        ↳ {s.rationale[:110]}")

        # Pull the comparison facets out even if they didn't make the top 8
        print("  -- key comparison facets (even if outside top 8) --")
        wanted = ("compassion-fatigue", "moroseness", "discontentment",
                  "stress-recovery-ability", "self-compassion")
        seen_compassion = False
        for s in t.scores:
            fid = s.facet_id
            if any(w in fid for w in wanted):
                print(f"    {s.facet_name[:40]:40s}  score={s.score}  conf={s.confidence:.2f}")
            elif fid == "compassion" and not seen_compassion:
                # Plain "Compassion" facet (not Compassion Fatigue)
                print(f"    {s.facet_name[:40]:40s}  score={s.score}  conf={s.confidence:.2f}")
                seen_compassion = True

    # Reference numbers from the qwen3:8b run for at-a-glance comparison.
    print()
    print("=" * 78)
    print("Reference (qwen3:8b on the same conversation):")
    print("  USER turn:")
    print("    Patient care orientation        score=3")
    print("    Compassion Fatigue              score=? (not retrieved)")
    print("  ASSISTANT turn:")
    print("    Cognitive Empathy               score=4   ← correct (high)")
    print("    Compassion Fatigue              score=2   ← correct conservative")
    print("    Compassion                      score=2   ← WRONG (should be 4-5)")
    print("    Moroseness                      score=2   ← correct (low)")
    print("    Discontentment                  not in top ← correct (low)")
    print()
    print("VERDICT for the alt model is good if:")
    print("  • Moroseness on assistant stays LOW (≤ 2-3)")
    print("  • Compassion on assistant goes UP (≥ 4)")
    print("  • Compassion Fatigue on USER turn ≥ 4 (or appears in retrieval)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
