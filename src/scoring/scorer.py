"""Stage-2 scorer: per-facet structured ordinal scoring.

The scorer does NOT see the entire facet catalogue — only the K facets
the retriever picked for the current turn. For each one it builds a
small focused prompt containing the facet name, definition, 5-level
rubric, the conversation context, and the target turn, then asks the
LLM for a JSON object ``{"score", "rationale", "evidence_span"}``.

The scorer is purposefully thin: all the prompt construction lives in
``src.models.llm_client.build_user_prompt``. This module's job is the
ordering / batching / caching policy.
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from src.models.llm_client import LLMClient, ScoreResult, _SYSTEM_PROMPT, _USER_TEMPLATE
from src.utils.logging import get_logger


def _current_prompt_version() -> str:
    """SHA1[:12] of the live system + user prompt templates.

    Any edit to the scoring prompt automatically rolls this hash, which
    rolls the cache key, which forces a re-query. Means the cache cannot
    serve stale results after a prompt change.
    """
    h = hashlib.sha1()
    h.update(_SYSTEM_PROMPT.encode("utf-8"))
    h.update(_USER_TEMPLATE.encode("utf-8"))
    return h.hexdigest()[:12]
from src.utils.types import (
    ConversationTurn,
    FacetDefinition,
    FacetScore,
    Speaker,
    TurnScores,
)

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Per-facet scoring (single turn, single facet)
# ---------------------------------------------------------------------------


def _score_one(
    client: LLMClient,
    facet: FacetDefinition,
    turn: ConversationTurn,
    context: list[ConversationTurn],
    cache: Optional["ScoreCache"] = None,
    temperature: float = 0.0,
) -> FacetScore:
    if cache is not None:
        cached = cache.get(facet.facet_id, turn)
        if cached is not None:
            return cached

    ctx_pairs = [(c.speaker.value, c.text) for c in context]
    res: ScoreResult = client.score(
        facet=facet,
        turn_text=turn.text,
        speaker=turn.speaker.value,
        context_turns=ctx_pairs,
        temperature=temperature,
    )
    fs = FacetScore(
        facet_id=facet.facet_id,
        facet_name=facet.name,
        score=res.score,
        confidence=res.confidence,
        rationale=res.rationale,
        evidence_span=res.evidence_span,
        score_distribution=res.score_distribution,
    )
    if cache is not None:
        cache.put(facet.facet_id, turn, fs)
    return fs


# ---------------------------------------------------------------------------
# Per-turn scoring (parallel across facets)
# ---------------------------------------------------------------------------


def score_turn(
    client: LLMClient,
    facets: list[FacetDefinition],
    turn: ConversationTurn,
    context: list[ConversationTurn],
    parallel_workers: int = 8,
    cache: Optional["ScoreCache"] = None,
) -> TurnScores:
    started = time.perf_counter()
    scores: list[FacetScore] = [None] * len(facets)  # type: ignore

    if parallel_workers <= 1:
        for i, f in enumerate(facets):
            scores[i] = _score_one(client, f, turn, context, cache)
    else:
        with ThreadPoolExecutor(max_workers=parallel_workers) as pool:
            futures = {
                pool.submit(_score_one, client, f, turn, context, cache): i
                for i, f in enumerate(facets)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                scores[i] = fut.result()

    return TurnScores(
        turn_index=turn.turn_index,
        speaker=turn.speaker,
        text=turn.text,
        retrieved_facet_ids=[f.facet_id for f in facets],
        scores=list(scores),
        latency_ms=(time.perf_counter() - started) * 1000.0,
    )


# ---------------------------------------------------------------------------
# Disk cache (turn × facet -> FacetScore)
# ---------------------------------------------------------------------------


class ScoreCache:
    """Tiny on-disk JSON cache. Keyed by SHA1(prompt_version, model, facet_id, speaker, turn_text).

    The ``prompt_version`` component is auto-derived from the live SYSTEM
    prompt in ``src.models.llm_client``, so any change to scoring prompt or
    rules invalidates the cache automatically — no more silent stale-output
    bugs after a prompt edit. Useful when iterating on prompts or rerunning
    the 50-conv suite. Disable in config.
    """

    def __init__(self, cache_dir: Path, model_tag: str, prompt_version: Optional[str] = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_tag = model_tag
        self.prompt_version = prompt_version or _current_prompt_version()

    def _key(self, facet_id: str, turn: ConversationTurn) -> str:
        h = hashlib.sha1()
        h.update(self.prompt_version.encode())
        h.update(self.model_tag.encode())
        h.update(facet_id.encode())
        h.update(turn.speaker.value.encode())
        h.update(turn.text.encode("utf-8"))
        return h.hexdigest()

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, facet_id: str, turn: ConversationTurn) -> Optional[FacetScore]:
        p = self._path(self._key(facet_id, turn))
        if not p.exists():
            return None
        try:
            return FacetScore.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def put(self, facet_id: str, turn: ConversationTurn, score: FacetScore) -> None:
        p = self._path(self._key(facet_id, turn))
        p.write_text(score.model_dump_json(), encoding="utf-8")
