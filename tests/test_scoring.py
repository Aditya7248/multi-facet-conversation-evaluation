"""Smoke tests for the scoring stack — uses the heuristic fallback so they
run in CI without a GPU or LLM service."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models.llm_client import (
    HeuristicClient,
    normalised_entropy_confidence,
)
from src.scoring.pipeline import ScoringPipeline
from src.scoring.retriever import build_default_retriever
from src.utils.types import (
    Conversation,
    ConversationTurn,
    FacetCategory,
    Speaker,
)

# ---------------------------------------------------------------------------
# Confidence math
# ---------------------------------------------------------------------------


def test_confidence_uniform_is_zero() -> None:
    p = [0.2, 0.2, 0.2, 0.2, 0.2]
    assert abs(normalised_entropy_confidence(p)) < 1e-6


def test_confidence_peaked_is_one() -> None:
    p = [1.0, 0.0, 0.0, 0.0, 0.0]
    assert normalised_entropy_confidence(p) > 0.999


def test_confidence_monotone() -> None:
    sharp = [0.6, 0.2, 0.1, 0.05, 0.05]
    flat = [0.3, 0.3, 0.2, 0.1, 0.1]
    assert normalised_entropy_confidence(sharp) > normalised_entropy_confidence(flat)


# ---------------------------------------------------------------------------
# Heuristic client schema
# ---------------------------------------------------------------------------


def _has_artefacts() -> bool:
    return (Path("data/index/facets.npy").exists()
            or Path("data/index/facets.faiss").exists())


@pytest.mark.skipif(not _has_artefacts(), reason="run `make data-all` first")
def test_heuristic_client_returns_valid_score() -> None:
    retriever = build_default_retriever()
    facets = retriever.retrieve("I am furious and exhausted.", top_k=3)
    assert facets, "retriever returned nothing"

    client = HeuristicClient()
    res = client.score(
        facet=facets[0].facet,
        turn_text="I am furious and exhausted.",
        speaker="user",
    )
    assert 1 <= res.score <= 5
    assert 0.0 <= res.confidence <= 1.0
    assert len(res.score_distribution) == 5
    assert abs(sum(res.score_distribution) - 1.0) < 1e-3


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_artefacts(), reason="run `make data-all` first")
def test_pipeline_scores_full_conversation() -> None:
    conv = Conversation(
        conversation_id="t-1",
        title="test",
        tags=["test"],
        turns=[
            ConversationTurn(turn_index=0, speaker=Speaker.USER, text="I'm thrilled today!"),
            ConversationTurn(turn_index=1, speaker=Speaker.ASSISTANT, text="That's wonderful — what's the news?"),
        ],
    )
    pipe = ScoringPipeline.default()
    result = pipe.score_conversation(conv, top_k=8)

    assert len(result.turn_scores) == 2
    for ts in result.turn_scores:
        assert ts.scores
        for s in ts.scores:
            assert 1 <= s.score <= 5
            assert 0.0 <= s.confidence <= 1.0
            assert len(s.score_distribution or []) == 5
    assert result.summary["n_facet_scores"] > 0
    assert "elapsed_seconds" in result.pipeline_meta


@pytest.mark.skipif(not _has_artefacts(), reason="run `make data-all` first")
def test_retriever_top_k_constant_in_facet_count() -> None:
    """Sanity-check that retrieval returns exactly K (or fewer) facets — this
    is the property that lets the architecture scale to 5000+ facets."""
    retriever = build_default_retriever()
    for k in (5, 10, 20, 40):
        hits = retriever.retrieve("I'm completely burned out from work.", top_k=k)
        assert len(hits) == k


@pytest.mark.skipif(not _has_artefacts(), reason="run `make data-all` first")
def test_category_filter_narrows_results() -> None:
    retriever = build_default_retriever()
    hits = retriever.retrieve(
        "I'm completely burned out.",
        top_k=10,
        category=FacetCategory.EMOTION,
    )
    for h in hits:
        assert h.facet.category == FacetCategory.EMOTION
