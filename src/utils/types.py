"""Pydantic schemas for the entire system.

These types are the single source of truth for the JSON shape of every
artefact produced by the pipeline (enriched facets, scored turns, API
payloads). Changing them is intentional — every consumer is type-checked
against these classes.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Facet domain model
# ---------------------------------------------------------------------------


class FacetCategory(str, Enum):
    LINGUISTIC_QUALITY = "linguistic_quality"
    PRAGMATICS = "pragmatics"
    SAFETY = "safety"
    EMOTION = "emotion"
    PERSONALITY = "personality"
    COGNITION_REASONING = "cognition_reasoning"
    RELATIONAL = "relational"
    CLINICAL_HEALTH = "clinical_health"
    BEHAVIORAL_LIFESTYLE = "behavioral_lifestyle"
    SPIRITUALITY_CULTURE = "spirituality_culture"
    OTHER = "other"


class ScoreDirection(str, Enum):
    """Whether a higher score means more or less of the trait.

    For most facets, higher = more (e.g. Risktaking 5 = very risk-taking).
    For some, higher could mean better (e.g. Common-sense 5 = excellent).
    Bipolar means score 3 is neutral, 1 and 5 are opposite extremes.
    """

    POSITIVE = "positive"   # higher score = more of the trait
    NEGATIVE = "negative"   # higher score = less of the trait (rare)
    BIPOLAR = "bipolar"     # 3 = neutral, 1 and 5 are opposites


class ApplicableSpeaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    BOTH = "both"


class RubricLevel(BaseModel):
    """A single anchor on the 5-point rubric."""

    level: int = Field(..., ge=1, le=5)
    label: str
    description: str
    exemplar: Optional[str] = None


class FacetDefinition(BaseModel):
    """The fully-enriched definition of a single evaluation facet.

    This is what the retriever indexes and what the scorer prompts with.
    Every field except `name` and `description` is auto-derivable, but
    every field is enforced so we can guarantee consistent behaviour as
    the facet set grows from 300 to 5000+.
    """

    facet_id: str = Field(..., description="Stable slug, e.g. 'compassion-fatigue'")
    name: str
    category: FacetCategory
    description: str
    rubric: list[RubricLevel] = Field(..., min_length=5, max_length=5)
    score_scale: list[int] = Field(default=[1, 2, 3, 4, 5], min_length=5, max_length=5)
    score_direction: ScoreDirection = ScoreDirection.POSITIVE
    applicable_speaker: ApplicableSpeaker = ApplicableSpeaker.BOTH
    keywords: list[str] = Field(default_factory=list)
    exemplars: list[str] = Field(default_factory=list)

    @field_validator("rubric")
    @classmethod
    def _check_rubric_levels(cls, v: list[RubricLevel]) -> list[RubricLevel]:
        levels = sorted(r.level for r in v)
        if levels != [1, 2, 3, 4, 5]:
            raise ValueError(f"Rubric must have exactly levels 1..5, got {levels}")
        return v

    def embed_text(self) -> str:
        """Concatenated text used to embed this facet for the routing index."""
        rubric_str = " ".join(f"L{r.level}: {r.description}" for r in self.rubric)
        kw = ", ".join(self.keywords) if self.keywords else ""
        return (
            f"{self.name}. Category: {self.category.value}. {self.description} "
            f"Rubric: {rubric_str} Keywords: {kw}"
        ).strip()


# ---------------------------------------------------------------------------
# Conversation domain model
# ---------------------------------------------------------------------------


class Speaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationTurn(BaseModel):
    turn_index: int = Field(..., ge=0)
    speaker: Speaker
    text: str

    def short_id(self) -> str:
        return f"t{self.turn_index:03d}-{self.speaker.value}"


class Conversation(BaseModel):
    conversation_id: str
    title: Optional[str] = None
    tags: list[str] = Field(default_factory=list, description="e.g. ['toxic', 'sarcasm']")
    turns: list[ConversationTurn]
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scoring domain model
# ---------------------------------------------------------------------------


class FacetScore(BaseModel):
    """One facet's score for one turn, with calibrated confidence."""

    facet_id: str
    facet_name: str
    score: int = Field(..., ge=1, le=5)
    confidence: float = Field(..., ge=0.0, le=1.0, description="0..1, calibrated")
    rationale: str = ""
    evidence_span: Optional[str] = None
    score_distribution: Optional[list[float]] = Field(
        default=None,
        description="Softmax probability over the 5 ordinal classes (sums to 1).",
    )

    @field_validator("score_distribution")
    @classmethod
    def _check_dist(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is None:
            return v
        if len(v) != 5:
            raise ValueError("score_distribution must have exactly 5 entries")
        if abs(sum(v) - 1.0) > 1e-3:
            raise ValueError(f"score_distribution must sum to 1.0, got {sum(v)}")
        return v


class TurnScores(BaseModel):
    """All facet scores for a single conversation turn."""

    turn_index: int
    speaker: Speaker
    text: str
    retrieved_facet_ids: list[str] = Field(default_factory=list)
    scores: list[FacetScore] = Field(default_factory=list)
    latency_ms: Optional[float] = None


class ConversationScores(BaseModel):
    """The top-level scoring artefact written to disk for each conversation."""

    conversation_id: str
    title: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    turn_scores: list[TurnScores]
    summary: dict = Field(default_factory=dict)
    pipeline_meta: dict = Field(default_factory=dict)
