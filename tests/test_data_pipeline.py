"""Integration tests for the data pipeline (clean -> enrich)."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from src.data_pipeline.clean import clean_facets
from src.data_pipeline.enrich import enrich
from src.utils.types import FacetCategory, FacetDefinition


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


def test_clean_dedupes_case_insensitively(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "Facets\nRisktaking\nrisktaking\nNaivety\nNaivety \n",
        encoding="utf-8",
    )
    out = tmp_path / "cleaned.csv"
    stats = clean_facets(raw, out)
    assert stats["dropped_duplicates"] >= 1
    df = pd.read_csv(out)
    assert df["name"].str.lower().is_unique


def test_clean_strips_numbered_prefix_and_trailing_colon(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "Facets\n793. Sufi practice: Dhikr / day\nDemocratic Leadership:\n",
        encoding="utf-8",
    )
    out = tmp_path / "cleaned.csv"
    clean_facets(raw, out)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    names = [r["name"] for r in rows]
    assert "Sufi practice: Dhikr / day" in names
    assert "Democratic Leadership" in names


def test_clean_drops_empty_rows(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text("Facets\nRisktaking\n\n  \nNaivety\n", encoding="utf-8")
    out = tmp_path / "cleaned.csv"
    stats = clean_facets(raw, out)
    assert stats["kept_rows"] == 2


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


def test_enrich_schema(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "Facets\nCompassion Fatigue\nStatistical Reasoning\nFSH level\nProcessed-food frequency\nRisktaking\n",
        encoding="utf-8",
    )
    cleaned = tmp_path / "cleaned.csv"
    clean_facets(raw, cleaned)

    enriched_csv = tmp_path / "enriched.csv"
    enriched_jsonl = tmp_path / "enriched.jsonl"
    stats = enrich(
        cleaned, enriched_csv, enriched_jsonl,
        embedder_name="sentence-transformers/all-MiniLM-L6-v2",
    )
    assert stats["n_facets"] == 5

    # Every line is a valid FacetDefinition with a 5-level rubric
    defs = [
        FacetDefinition.model_validate_json(line)
        for line in enriched_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(defs) == 5
    for d in defs:
        assert isinstance(d.category, FacetCategory)
        assert sorted(r.level for r in d.rubric) == [1, 2, 3, 4, 5]
        assert d.score_scale == [1, 2, 3, 4, 5]
        # embed_text must be non-empty and contain the facet name
        assert d.name in d.embed_text()


def test_enrich_categorisation_specific(tmp_path: Path) -> None:
    """High-precision spot-checks: keyword fast path should pin obvious facets."""
    raw = tmp_path / "raw.csv"
    raw.write_text("Facets\nCompassion Fatigue\nStatistical Reasoning\nFSH level\n", encoding="utf-8")
    cleaned = tmp_path / "cleaned.csv"
    clean_facets(raw, cleaned)

    enriched_csv = tmp_path / "enriched.csv"
    enriched_jsonl = tmp_path / "enriched.jsonl"
    enrich(cleaned, enriched_csv, enriched_jsonl,
           embedder_name="sentence-transformers/all-MiniLM-L6-v2")

    defs = {
        d.name: d
        for d in (
            FacetDefinition.model_validate_json(line)
            for line in enriched_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    # Compassion fatigue is in the relational/emotion family
    assert defs["Compassion Fatigue"].category in {
        FacetCategory.RELATIONAL,
        FacetCategory.EMOTION,
    }
    # FSH level is clinical
    assert defs["FSH level"].category == FacetCategory.CLINICAL_HEALTH
    # Statistical reasoning is cognition
    assert defs["Statistical Reasoning"].category == FacetCategory.COGNITION_REASONING
