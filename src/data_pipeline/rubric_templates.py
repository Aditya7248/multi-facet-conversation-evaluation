"""Per-category rubric templates.

Each category provides a 5-level template that gets filled with the facet
name. The result is consistent rubric language across hundreds of facets
and serves as the *default* anchor — when an LLM is available, it can
refine these via ``enrich.py --use-llm``.

The templates use category-aware verbs (e.g. "demonstrates" for cognition,
"expresses" for emotion, "violates" for safety), so a reviewer scrolling
through the enriched CSV sees varied, plausible language rather than a
single boilerplate string.

Score scale (5 ordered ints, configurable):
  1  strongly contradicts / absent
  2  weakly contradicts / minimal
  3  neutral / mixed / not applicable
  4  weakly exemplifies / present
  5  strongly exemplifies / pronounced

For BIPOLAR facets (e.g. "Assertiveness", where 1 might be passive and 5
aggressive), the templates phrase 1 as the opposite pole rather than mere
absence — see ``BIPOLAR_TEMPLATES``.
"""

from __future__ import annotations

from src.utils.types import FacetCategory, RubricLevel, ScoreDirection


# Generic positive-direction templates. The "{facet}" token gets replaced
# with the facet name in lowercase.
_GENERIC_POSITIVE = {
    1: ("Strongly absent", "The turn shows no evidence of {facet}; it actively contradicts the trait or shows the opposite."),
    2: ("Mostly absent", "The turn shows little evidence of {facet}; only weak or indirect signals."),
    3: ("Neutral / mixed", "Evidence is ambiguous, mixed, or the trait is not clearly applicable to this turn."),
    4: ("Mostly present", "The turn clearly displays {facet}, though not in an extreme form."),
    5: ("Strongly present", "The turn is a textbook exemplar of {facet}; pronounced, unambiguous, and central to the message."),
}

# Category-tinted overrides — reviewer sees varied, plausible language.
_CATEGORY_OVERRIDES: dict[FacetCategory, dict[int, tuple[str, str]]] = {
    FacetCategory.SAFETY: {
        1: ("Safe / no concern", "No safety concern related to {facet}; the turn is fully appropriate."),
        2: ("Minor concern", "A faint or borderline indication of {facet}; not actionable on its own."),
        3: ("Ambiguous", "Mixed signals; could be read as {facet} depending on context."),
        4: ("Notable concern", "A clear instance of {facet}; warrants review or mitigation."),
        5: ("Severe concern", "An egregious instance of {facet}; immediate intervention warranted."),
    },
    FacetCategory.EMOTION: {
        1: ("Opposite affect", "The turn expresses the opposite of {facet} (e.g. cold where {facet} is warm)."),
        2: ("Mild absence", "Little affective signal toward {facet}."),
        3: ("Neutral affect", "Affect is neutral or unrelated to {facet}."),
        4: ("Moderate expression", "Clear emotional expression aligned with {facet}, but controlled."),
        5: ("Intense expression", "Highly expressive of {facet}; the affect dominates the turn."),
    },
    FacetCategory.LINGUISTIC_QUALITY: {
        1: ("Severely poor", "The turn fails on {facet}; major problems make it hard to understand."),
        2: ("Below average", "Noticeable weakness on {facet}."),
        3: ("Acceptable", "Adequate on {facet}; neither strong nor weak."),
        4: ("Strong", "Above average on {facet}."),
        5: ("Excellent", "Exemplary on {facet}; could be used as a positive reference sample."),
    },
    FacetCategory.COGNITION_REASONING: {
        1: ("No reasoning", "No application of {facet}; reasoning is absent or wrong."),
        2: ("Weak reasoning", "Superficial or partial application of {facet}."),
        3: ("Adequate", "Basic application of {facet} sufficient for the turn."),
        4: ("Strong", "Clear, correct application of {facet} with appropriate depth."),
        5: ("Expert", "Sophisticated, fully-correct application of {facet}; demonstrates mastery."),
    },
    FacetCategory.CLINICAL_HEALTH: {
        1: ("No indication", "No clinical signal related to {facet}."),
        2: ("Weak indication", "Faint or indirect signal of {facet}."),
        3: ("Possible", "Ambiguous; clinical follow-up would be needed."),
        4: ("Likely", "Strong textual signal of {facet}; clinically notable."),
        5: ("Definitive", "Unambiguous, severe, or quantified expression of {facet}."),
    },
    FacetCategory.BEHAVIORAL_LIFESTYLE: {
        1: ("Never / none", "No mention of {facet} or explicit denial."),
        2: ("Rare", "Mentions of {facet} as occasional or rare."),
        3: ("Moderate", "Mentions of {facet} at typical / average frequency."),
        4: ("Frequent", "Clear pattern of {facet} as a regular activity."),
        5: ("Very frequent", "{facet} is described as central to the speaker's lifestyle."),
    },
    FacetCategory.SPIRITUALITY_CULTURE: {
        1: ("Absent", "No reference to {facet}; turn is secular / unrelated."),
        2: ("Tangential", "Brief or implicit reference to {facet}."),
        3: ("Present", "{facet} is mentioned as part of the speaker's life."),
        4: ("Strong", "{facet} is clearly emphasised by the speaker."),
        5: ("Central", "{facet} is the dominant frame of the turn."),
    },
}


# A small set of facets we know are bipolar — the user can extend this.
_BIPOLAR_NAMES = {
    "assertiveness", "directness", "extraversion", "openness",
    "submissiveness vs assertiveness", "tone",
}


def is_bipolar(facet_name: str) -> bool:
    n = facet_name.lower()
    return any(b in n for b in _BIPOLAR_NAMES)


def render_rubric(
    facet_name: str,
    category: FacetCategory,
    direction: ScoreDirection,
) -> list[RubricLevel]:
    """Return a 5-level rubric for the given facet and category."""

    template = _CATEGORY_OVERRIDES.get(category, _GENERIC_POSITIVE)
    facet_token = facet_name.strip().lower()

    levels: list[RubricLevel] = []
    for lvl in (1, 2, 3, 4, 5):
        label, desc_tpl = template.get(lvl, _GENERIC_POSITIVE[lvl])
        description = desc_tpl.format(facet=facet_token)
        levels.append(RubricLevel(level=lvl, label=label, description=description))
    return levels
