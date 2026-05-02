"""End-to-end orchestrator.

Public API:

    pipe = ScoringPipeline.default()
    result = pipe.score_conversation(conversation, top_k=40)

It composes the retriever, the LLM client, and the scorer, exposes a
small in-memory + disk cache, computes a per-conversation summary
(category-level means, top facets by score, low-confidence flags), and
records pipeline metadata so the artefacts on disk are reproducible.
"""

from __future__ import annotations

import time
from pathlib import Path

from src.models.llm_client import LLMClient, build_default_client
from src.scoring.retriever import FacetRetriever, build_default_retriever
from src.scoring.scorer import ScoreCache, score_turn
from src.utils.config import load_config
from src.utils.logging import get_logger
from src.utils.types import (
    Conversation,
    ConversationScores,
    FacetCategory,
    TurnScores,
)

log = get_logger(__name__)


class ScoringPipeline:
    def __init__(
        self,
        retriever: FacetRetriever,
        client: LLMClient,
        top_k: int = 40,
        parallel_workers: int = 8,
        cache: ScoreCache | None = None,
        category_filter: FacetCategory | None = None,
        min_retrieval_score: float = 0.0,
    ):
        self.retriever = retriever
        self.client = client
        self.top_k = top_k
        self.parallel_workers = parallel_workers
        self.cache = cache
        self.category_filter = category_filter
        self.min_retrieval_score = min_retrieval_score

    # ---- Constructors -------------------------------------------------

    @classmethod
    def default(cls) -> ScoringPipeline:
        cfg = load_config()
        retriever = build_default_retriever()
        client = build_default_client()
        cache: ScoreCache | None = None
        if cfg["scoring"].get("cache_enabled", True):
            cache = ScoreCache(
                cache_dir=Path(cfg["repo_root"]) / cfg["scoring"]["cache_dir"]
                if not Path(cfg["scoring"]["cache_dir"]).is_absolute()
                else Path(cfg["scoring"]["cache_dir"]),
                model_tag=client.name,
            )
        return cls(
            retriever=retriever,
            client=client,
            top_k=int(cfg["retrieval"]["top_k"]),
            parallel_workers=int(cfg["scoring"]["parallel_workers"]),
            cache=cache,
            min_retrieval_score=float(cfg["retrieval"].get("min_score_threshold", 0.0)),
        )

    # ---- Public API ----------------------------------------------------

    def score_conversation(
        self, conversation: Conversation, top_k: int | None = None
    ) -> ConversationScores:
        k = top_k or self.top_k
        log.info(
            "Scoring conversation '%s' (%d turns) — top_k=%d, backend=%s",
            conversation.conversation_id, len(conversation.turns), k, self.client.name,
        )
        started = time.perf_counter()
        turn_scores: list[TurnScores] = []

        for turn in conversation.turns:
            context = conversation.turns[: turn.turn_index]   # all prior turns
            retrieved = self.retriever.retrieve(
                turn.text,
                top_k=k,
                category=self.category_filter,
                min_score=self.min_retrieval_score,
            )
            if not retrieved:
                turn_scores.append(
                    TurnScores(
                        turn_index=turn.turn_index,
                        speaker=turn.speaker,
                        text=turn.text,
                        retrieved_facet_ids=[],
                        scores=[],
                        latency_ms=0.0,
                    )
                )
                continue

            facets = [r.facet for r in retrieved]
            ts = score_turn(
                client=self.client,
                facets=facets,
                turn=turn,
                context=context,
                parallel_workers=self.parallel_workers,
                cache=self.cache,
            )
            turn_scores.append(ts)

        elapsed_s = time.perf_counter() - started
        result = ConversationScores(
            conversation_id=conversation.conversation_id,
            title=conversation.title,
            tags=conversation.tags,
            turn_scores=turn_scores,
            summary=summarise_conversation(turn_scores),
            pipeline_meta={
                "client": self.client.name,
                "retriever_dim": self.retriever.meta.get("dim"),
                "embedder": self.retriever.meta.get("embedder"),
                "n_facets_indexed": self.retriever.meta.get("n_facets"),
                "top_k": k,
                "parallel_workers": self.parallel_workers,
                "elapsed_seconds": round(elapsed_s, 3),
            },
        )
        log.info(
            "  ↳ scored %d turns × ~%d facets in %.2fs",
            len(turn_scores), k, elapsed_s,
        )
        return result


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def summarise_conversation(turns: list[TurnScores]) -> dict:
    """Compute an at-a-glance summary used by the UI and the deliverable."""
    summary: dict = {
        "n_turns": len(turns),
        "n_facet_scores": sum(len(t.scores) for t in turns),
        "avg_confidence": 0.0,
        "low_confidence_flags": [],
        "top_facets_by_mean_score": [],
        "category_means": {},
    }

    all_scores = [s for t in turns for s in t.scores]
    if not all_scores:
        return summary

    summary["avg_confidence"] = sum(s.confidence for s in all_scores) / len(all_scores)

    # Aggregate per-facet across turns
    by_facet: dict[str, list[float]] = {}
    for s in all_scores:
        by_facet.setdefault(s.facet_id, []).append(s.score)

    means = sorted(
        ({"facet_id": fid, "mean_score": sum(v) / len(v), "n_observations": len(v)}
         for fid, v in by_facet.items()),
        key=lambda r: r["mean_score"],
        reverse=True,
    )
    summary["top_facets_by_mean_score"] = means[:10]

    # Low-confidence flags (any score with confidence below 0.4)
    summary["low_confidence_flags"] = [
        {"turn_index": t.turn_index, "facet_id": s.facet_id, "confidence": s.confidence}
        for t in turns for s in t.scores if s.confidence < 0.4
    ][:50]

    return summary
