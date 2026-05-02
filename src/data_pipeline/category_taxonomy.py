"""Category taxonomy used by the auto-categorizer.

Each category has a list of seed terms and a one-sentence description.
The enrichment step computes embedding similarity between the facet text
and each category's seed phrases, then picks the argmax (with a keyword
fast-path for high-precision matches).

Adding a new category here requires no other code change.
"""

from __future__ import annotations

from src.utils.types import FacetCategory

CATEGORY_PROFILES: dict[FacetCategory, dict] = {
    FacetCategory.LINGUISTIC_QUALITY: {
        "description": "Surface-level language qualities of an utterance: fluency, coherence, "
        "specificity, conciseness, grammar, vocabulary range.",
        "seeds": [
            "fluency", "grammar", "vocabulary", "coherence", "clarity", "concision",
            "verbosity", "ambiguity", "specificity", "readability", "redundancy",
            "alphanumeric", "syntax",
        ],
        "keywords": ["fluen", "gramm", "vocab", "coheren", "clarity", "concis", "redund",
                     "syntax", "spelling", "punctuation", "readab"],
    },
    FacetCategory.PRAGMATICS: {
        "description": "Communicative intent and discourse moves: politeness, directness, "
        "irony, hedging, turn-taking, repair, presupposition.",
        "seeds": [
            "politeness", "directness", "hedging", "irony", "sarcasm", "implicature",
            "tone", "register", "presupposition", "speech act", "conversational repair",
            "turn taking", "topic shift",
        ],
        "keywords": ["politeness", "hedge", "irony", "sarcasm", "tone", "register",
                     "implicat", "discour", "pragmat"],
    },
    FacetCategory.SAFETY: {
        "description": "Risk, harm, toxicity, manipulation, deception, privacy violations, "
        "bias and fairness concerns.",
        "seeds": [
            "toxicity", "harassment", "violence", "self-harm", "manipulation", "deception",
            "bias", "fairness", "privacy", "PII", "harmful content", "extremism",
            "misinformation", "jailbreak", "disrespect", "hostility",
        ],
        "keywords": ["toxic", "harm", "violen", "manipulat", "decep", "bias", "privacy",
                     "abus", "hostil", "disrespect", "hate", "threat"],
    },
    FacetCategory.EMOTION: {
        "description": "Affect and emotional content: valence, arousal, specific emotions, "
        "emotional regulation, empathy, compassion.",
        "seeds": [
            "happiness", "sadness", "anger", "fear", "disgust", "surprise",
            "merriness", "moroseness", "discontentment", "compassion", "empathy",
            "negative affect", "positive affect", "emotional regulation", "warmth",
            "emotionalism", "sensitivity", "peacefulness",
        ],
        "keywords": ["emotion", "affect", "merr", "morose", "compass", "empath",
                     "discontent", "sens", "warmth", "joy", "anger", "sadness", "peace"],
    },
    FacetCategory.PERSONALITY: {
        "description": "Stable traits and dispositions: HEXACO/Big-Five facets, character "
        "strengths, virtues, leadership style.",
        "seeds": [
            "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism",
            "honesty", "humility", "modesty", "naivety", "risktaking", "submissiveness",
            "assertiveness", "doggedness", "decency", "chivalrousness", "genuine",
            "determinedness", "structure", "self-esteem", "self-perspective",
            "democratic leadership", "specialist",
        ],
        "keywords": ["personality", "trait", "honesty", "humility", "naiv", "risktak",
                     "submiss", "assert", "decency", "chivalr", "leadership", "esteem"],
    },
    FacetCategory.COGNITION_REASONING: {
        "description": "Thinking processes: reasoning, problem-solving, learning, memory, "
        "creativity, common-sense.",
        "seeds": [
            "common sense", "statistical reasoning", "numerical reasoning", "logic",
            "innovation", "creativity", "learning", "self-improvement", "specialist knowledge",
            "anatomy knowledge", "comparing alphanumeric data",
            "training-cycle length", "structure",
        ],
        "keywords": ["reasoning", "logic", "creativ", "innov", "knowledge", "learning",
                     "common-sense", "anatomy", "numerical", "statistical", "cogniti"],
    },
    FacetCategory.RELATIONAL: {
        "description": "Interpersonal style and relationship dynamics: cooperation, conflict, "
        "trust, intimacy, control, attachment.",
        "seeds": [
            "relationship building", "assertiveness in relationships", "control",
            "cunningness", "passive-aggressive", "overprotectiveness", "affiliation motivation",
            "compassion fatigue", "aloofness", "big-heartedness", "hesitation",
        ],
        "keywords": ["relation", "interpersonal", "cooperat", "conflict", "trust",
                     "intimacy", "control", "passive-aggress", "overprotect", "affiliat",
                     "aloof", "big-hearted"],
    },
    FacetCategory.CLINICAL_HEALTH: {
        "description": "Clinical, medical, or physiological signals: hormone levels, "
        "anatomical knowledge, symptoms, mental-health markers.",
        "seeds": [
            "FSH level", "anatomy knowledge", "symptom", "diagnosis",
            "compulsive activities", "negative affect frequency",
            "presence of spiritual pain", "moroseness", "acidity",
        ],
        "keywords": ["fsh", "level", "hormone", "symptom", "diagnos", "clinic",
                     "anatomy", "compuls", "acidity", "pain"],
    },
    FacetCategory.BEHAVIORAL_LIFESTYLE: {
        "description": "Habitual behaviour patterns: diet, activities, hobbies, "
        "lifestyle frequencies and counts.",
        "seeds": [
            "eco-tourism trips", "pilgrimage participation count", "training-cycle length",
            "processed-food frequency", "adventure-seeking behavior",
        ],
        "keywords": ["frequency", "trips", "count", "cycle", "behavior", "lifestyle",
                     "habit", "tourism", "food", "adventure"],
    },
    FacetCategory.SPIRITUALITY_CULTURE: {
        "description": "Spirituality, religion, culture, mindfulness practices.",
        "seeds": [
            "mindfulness", "spirituality", "spiritual pain", "pilgrimage",
            "sufi practice", "dhikr", "role of spirituality in community involvement",
        ],
        "keywords": ["spiritual", "pilgrim", "sufi", "dhikr", "mindful",
                     "religio", "faith", "meditation"],
    },
    FacetCategory.OTHER: {
        "description": "Catch-all for facets that don't fit the above categories.",
        "seeds": ["miscellaneous", "uncategorized"],
        "keywords": [],
    },
}


def category_seed_text(cat: FacetCategory) -> str:
    """Concatenate description + seeds, used for embedding the category centroid."""
    profile = CATEGORY_PROFILES[cat]
    return f"{profile['description']} Examples: {', '.join(profile['seeds'])}."
