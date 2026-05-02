"""Quick smoke test for the live scoring pipeline.

Scores one canonical compassion-fatigue conversation and prints the top facets
per turn. Used to verify (a) the LLM backend is wired in, (b) the scoring
prompt produces inference-style reasoning rather than keyword matching, and
(c) the score range actually spans 1..5.

Run:
    PYTHONPATH=. python scripts/smoke_test.py
"""

from __future__ import annotations

from src.scoring.pipeline import ScoringPipeline
from src.utils.types import Conversation, ConversationTurn, Speaker


CONV = Conversation(
    conversation_id="smoke-real-v2",
    title="Burnout disclosure",
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


def main() -> None:
    pipe = ScoringPipeline.default()
    res = pipe.score_conversation(CONV, top_k=20)

    print("=" * 78)
    print(f"Backend:   {res.pipeline_meta['client']}")
    print(f"Embedder:  {res.pipeline_meta['embedder']}")
    print(f"Latency:   {res.pipeline_meta['elapsed_seconds']:.1f}s")
    print("=" * 78)

    # Quick spread check across all scores
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

        # Compassion-fatigue specific check (canonical inference test)
        cf = next(
            (s for s in t.scores if "compassion-fatigue" in s.facet_id or "fatigue" in s.facet_id),
            None,
        )
        if cf is not None:
            marker = "PASS" if cf.score >= 4 else "FAIL"
            print(f"    [Compassion Fatigue check]  score={cf.score}  --> {marker}")


if __name__ == "__main__":
    main()
