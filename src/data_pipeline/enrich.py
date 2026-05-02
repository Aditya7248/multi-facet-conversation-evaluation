"""Step 2: enrich the cleaned facet list.

For every cleaned facet we attach:

    - category              (one of the 11 in category_taxonomy.CATEGORY_PROFILES)
    - description           (one-paragraph definition)
    - rubric                (5 anchored levels — see rubric_templates)
    - score_scale           (default [1..5])
    - score_direction       (positive / negative / bipolar)
    - applicable_speaker    (user / assistant / both)
    - keywords              (auto-derived tokens for hybrid retrieval)
    - exemplars             (mini examples; LLM-filled when --use-llm is set)

Categorisation strategy (deterministic, no LLM by default):

    1. KEYWORD FAST-PATH. If the facet name contains a high-precision
       keyword from CATEGORY_PROFILES[*]['keywords'], we assign that
       category immediately (precision ~ 1).
    2. EMBEDDING ARGMAX. Otherwise, we embed the facet text and each
       category's seed text using sentence-transformers and pick the
       category with highest cosine similarity. This handles weird
       facets ("Pilgrimage participation count") gracefully.
    3. THRESHOLD GUARD. If the top similarity is below a small floor
       (configurable), the category is set to ``other``.

Run:

    python -m src.data_pipeline.enrich
    python -m src.data_pipeline.enrich --use-llm   # requires Ollama up

Outputs:
    data/processed/facets_enriched.csv     (flat, reviewer-friendly)
    data/processed/facets_enriched.jsonl   (the canonical artefact)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.data_pipeline.category_taxonomy import CATEGORY_PROFILES, category_seed_text
from src.data_pipeline.rubric_templates import is_bipolar, render_rubric
from src.utils.config import load_config
from src.utils.logging import get_logger
from src.utils.types import (
    ApplicableSpeaker,
    FacetCategory,
    FacetDefinition,
    ScoreDirection,
)

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Embedding-based categorisation
# ---------------------------------------------------------------------------


def _load_embedder(model_name: str):
    from src.utils.embeddings import build_embedder

    log.info("Loading embedder: %s", model_name)
    return build_embedder(model_name)


def _embed(model, texts: list[str]) -> np.ndarray:
    return model.encode(texts)


def _keyword_match(name: str) -> Optional[FacetCategory]:
    """High-precision keyword fast-path. Returns None if no match."""
    n = name.lower()
    for cat, profile in CATEGORY_PROFILES.items():
        for kw in profile.get("keywords", []):
            if kw in n:
                return cat
    return None


def _categorize_by_embedding(
    facet_vecs: np.ndarray, cat_vecs: np.ndarray, cat_keys: list[FacetCategory]
) -> tuple[list[FacetCategory], np.ndarray]:
    sims = facet_vecs @ cat_vecs.T          # (n_facets, n_cats), already L2-normalised
    idx = sims.argmax(axis=1)
    top_sim = sims.max(axis=1)
    return [cat_keys[i] for i in idx], top_sim


# ---------------------------------------------------------------------------
# Speaker / direction heuristics
# ---------------------------------------------------------------------------


_USER_HINTS = ("self-perspective", "self esteem", "self-improvement", "presence of",
               "compassion fatigue", "discontentment", "moroseness", "merriness")
_ASSISTANT_HINTS = ("democratic leadership", "specialist", "structure")


def _infer_speaker(name: str) -> ApplicableSpeaker:
    n = name.lower()
    if any(h in n for h in _USER_HINTS):
        return ApplicableSpeaker.USER
    if any(h in n for h in _ASSISTANT_HINTS):
        return ApplicableSpeaker.ASSISTANT
    return ApplicableSpeaker.BOTH


def _infer_direction(name: str) -> ScoreDirection:
    if is_bipolar(name):
        return ScoreDirection.BIPOLAR
    return ScoreDirection.POSITIVE


def _make_description(name: str, category: FacetCategory) -> str:
    profile = CATEGORY_PROFILES[category]
    return (
        f"'{name}' is a {category.value.replace('_', ' ')} facet. "
        f"Definition context: {profile['description']} "
        f"For this facet specifically, the score reflects how strongly the conversational turn "
        f"exhibits '{name.lower()}'."
    )


def _extract_keywords(name: str) -> list[str]:
    tokens = [t.lower() for t in name.replace("-", " ").split() if len(t) > 2]
    # de-duplicate while preserving order
    seen = set()
    return [t for t in tokens if not (t in seen or seen.add(t))]


# ---------------------------------------------------------------------------
# Optional LLM polish
# ---------------------------------------------------------------------------


def _maybe_llm_refine(defs: list[FacetDefinition]) -> list[FacetDefinition]:
    """Optional rubric polish via the configured LLM client.

    We import lazily so the default path never imports llm_client (which
    pulls httpx + tenacity). Failures are tolerated — we keep the template
    rubric and log a warning.
    """
    try:
        from src.models.llm_client import build_default_client
    except Exception as e:  # pragma: no cover
        log.warning("LLM client unavailable, skipping --use-llm polish: %s", e)
        return defs

    try:
        client = build_default_client()
    except Exception as e:
        log.warning("Could not start LLM client (%s); falling back to template rubrics.", e)
        return defs

    refined: list[FacetDefinition] = []
    for d in tqdm(defs, desc="LLM-refining rubrics", unit="facet"):
        try:
            refined.append(client.refine_facet(d))
        except Exception as e:
            log.debug("Refine failed for %s: %s", d.name, e)
            refined.append(d)
    return refined


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def enrich(
    cleaned_path: Path,
    enriched_csv: Path,
    enriched_jsonl: Path,
    embedder_name: str,
    use_llm: bool = False,
    sim_floor: float = 0.18,
) -> dict:
    df = pd.read_csv(cleaned_path)
    log.info("Loaded %d cleaned facets from %s", len(df), cleaned_path)

    # --- 1. Embedding setup --------------------------------------------------
    embedder = _load_embedder(embedder_name)
    cat_keys = list(CATEGORY_PROFILES.keys())
    cat_texts = [category_seed_text(c) for c in cat_keys]
    cat_vecs = _embed(embedder, cat_texts)
    facet_vecs = _embed(embedder, df["name"].tolist())

    # --- 2. Categorisation ---------------------------------------------------
    cats_by_embed, top_sims = _categorize_by_embedding(facet_vecs, cat_vecs, cat_keys)

    final_cats: list[FacetCategory] = []
    fastpath_hits = 0
    for i, name in enumerate(df["name"].tolist()):
        cat = _keyword_match(name)
        if cat is not None:
            fastpath_hits += 1
            final_cats.append(cat)
        elif top_sims[i] < sim_floor:
            final_cats.append(FacetCategory.OTHER)
        else:
            final_cats.append(cats_by_embed[i])

    # --- 3. Build FacetDefinition list --------------------------------------
    defs: list[FacetDefinition] = []
    for i, row in df.iterrows():
        name = row["name"]
        cat = final_cats[i]
        direction = _infer_direction(name)
        defs.append(
            FacetDefinition(
                facet_id=row["facet_id"],
                name=name,
                category=cat,
                description=_make_description(name, cat),
                rubric=render_rubric(name, cat, direction),
                score_scale=[1, 2, 3, 4, 5],
                score_direction=direction,
                applicable_speaker=_infer_speaker(name),
                keywords=_extract_keywords(name),
                exemplars=[],
            )
        )

    if use_llm:
        defs = _maybe_llm_refine(defs)

    # --- 4. Write artefacts --------------------------------------------------
    enriched_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with enriched_jsonl.open("w", encoding="utf-8") as fh:
        for d in defs:
            fh.write(d.model_dump_json() + "\n")

    flat = [
        {
            "facet_id": d.facet_id,
            "name": d.name,
            "category": d.category.value,
            "score_direction": d.score_direction.value,
            "applicable_speaker": d.applicable_speaker.value,
            "description": d.description,
            "rubric_1": d.rubric[0].description,
            "rubric_2": d.rubric[1].description,
            "rubric_3": d.rubric[2].description,
            "rubric_4": d.rubric[3].description,
            "rubric_5": d.rubric[4].description,
            "keywords": ", ".join(d.keywords),
        }
        for d in defs
    ]
    pd.DataFrame(flat).to_csv(enriched_csv, index=False)

    cat_counts = pd.Series([d.category.value for d in defs]).value_counts().to_dict()
    stats = {
        "n_facets": len(defs),
        "category_counts": cat_counts,
        "keyword_fast_path_hits": fastpath_hits,
        "embedder": embedder_name,
        "use_llm": use_llm,
    }
    log.info("[bold green]Enrichment complete[/]  %s", json.dumps(stats, indent=2))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich cleaned facets with categories + rubrics.")
    parser.add_argument("--cleaned", type=Path, default=None)
    parser.add_argument("--out-csv", type=Path, default=None)
    parser.add_argument("--out-jsonl", type=Path, default=None)
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Refine rubrics with the configured LLM (slow, requires Ollama/vLLM up).",
    )
    args = parser.parse_args()

    cfg = load_config()
    cleaned = args.cleaned or Path(cfg["paths"]["cleaned_facets"])
    out_csv = args.out_csv or Path(cfg["paths"]["enriched_facets"])
    out_jsonl = args.out_jsonl or Path(cfg["paths"]["enriched_jsonl"])
    embedder = cfg["embedding"]["model"]

    if not cleaned.exists():
        raise FileNotFoundError(
            f"Cleaned facets not found at {cleaned}. Run `make data-clean` first."
        )

    enrich(cleaned, out_csv, out_jsonl, embedder, use_llm=args.use_llm)


if __name__ == "__main__":
    main()
