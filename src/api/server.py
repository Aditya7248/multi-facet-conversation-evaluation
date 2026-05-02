"""FastAPI service: HTTP surface for the scoring pipeline.

Endpoints:

    GET  /health                       liveness + backend tag
    GET  /facets                       list every enriched facet (paginated)
    GET  /facets/{facet_id}            full record for one facet
    POST /retrieve                     top-K facets for a single turn
    POST /score                        score a full conversation
    POST /score/turn                   score a single turn against retrieved facets

The service is intentionally stateless — the pipeline is built on
startup and reused across requests via FastAPI's dependency-injection.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.scoring.pipeline import ScoringPipeline
from src.utils.config import load_config
from src.utils.logging import get_logger
from src.utils.types import (
    Conversation,
    ConversationScores,
    ConversationTurn,
    FacetCategory,
    FacetDefinition,
    Speaker,
)

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# App + dependency
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Ocean Across — Conversation Evaluation",
    version="0.1.0",
    description="Multi-facet conversation evaluation benchmark. Multi-stage retrieve-then-score pipeline over open-weights LLMs (≤16B). Scales to 5000+ facets without redesign.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_pipeline() -> ScoringPipeline:
    return ScoringPipeline.default()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    conversation: Conversation
    top_k: Optional[int] = Field(default=None, ge=1, le=400)
    category: Optional[FacetCategory] = None


class TurnScoreRequest(BaseModel):
    text: str
    speaker: Speaker = Speaker.USER
    context: list[ConversationTurn] = Field(default_factory=list)
    top_k: Optional[int] = Field(default=None, ge=1, le=400)
    category: Optional[FacetCategory] = None


class RetrieveRequest(BaseModel):
    text: str
    top_k: int = 40
    category: Optional[FacetCategory] = None
    min_score: float = 0.0


class RetrievedFacetOut(BaseModel):
    facet_id: str
    name: str
    category: FacetCategory
    score: float
    rank: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health(pipe: ScoringPipeline = Depends(get_pipeline)) -> dict:
    cfg = load_config()
    return {
        "status": "ok",
        "backend": pipe.client.name,
        "embedder": pipe.retriever.meta.get("embedder"),
        "n_facets": pipe.retriever.meta.get("n_facets"),
        "default_top_k": pipe.top_k,
        "version": "0.1.0",
        "config": {
            "score_levels": cfg["scoring"]["score_levels"],
            "parallel_workers": pipe.parallel_workers,
        },
    }


@app.get("/facets")
def list_facets(
    pipe: ScoringPipeline = Depends(get_pipeline),
    category: Optional[FacetCategory] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict:
    facets = pipe.retriever.all_facets()
    if category is not None:
        facets = [f for f in facets if f.category == category]
    total = len(facets)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [f.model_dump() for f in facets[start:end]],
    }


@app.get("/facets/{facet_id}")
def get_facet(facet_id: str, pipe: ScoringPipeline = Depends(get_pipeline)) -> FacetDefinition:
    try:
        return pipe.retriever.by_id(facet_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown facet_id: {facet_id}") from e


@app.post("/retrieve", response_model=list[RetrievedFacetOut])
def retrieve(req: RetrieveRequest, pipe: ScoringPipeline = Depends(get_pipeline)):
    hits = pipe.retriever.retrieve(
        req.text, top_k=req.top_k, category=req.category, min_score=req.min_score
    )
    return [
        RetrievedFacetOut(
            facet_id=h.facet.facet_id,
            name=h.facet.name,
            category=h.facet.category,
            score=h.score,
            rank=h.rank,
        )
        for h in hits
    ]


@app.post("/score", response_model=ConversationScores)
def score_conversation(req: ScoreRequest, pipe: ScoringPipeline = Depends(get_pipeline)):
    if req.category is not None:
        # Temporarily override the pipeline category filter for this call.
        pipe.category_filter = req.category
    try:
        return pipe.score_conversation(req.conversation, top_k=req.top_k)
    finally:
        pipe.category_filter = None


@app.post("/score/turn")
def score_single_turn(req: TurnScoreRequest, pipe: ScoringPipeline = Depends(get_pipeline)):
    """Convenience endpoint: score one turn without wrapping it in a Conversation."""
    turns = list(req.context) + [
        ConversationTurn(turn_index=len(req.context), speaker=req.speaker, text=req.text),
    ]
    conv = Conversation(
        conversation_id="adhoc",
        turns=turns,
    )
    if req.category is not None:
        pipe.category_filter = req.category
    try:
        result = pipe.score_conversation(conv, top_k=req.top_k)
    finally:
        pipe.category_filter = None
    return result.turn_scores[-1]
