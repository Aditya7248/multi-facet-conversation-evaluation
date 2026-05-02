"""Build a single Markdown digest of the bulk-run results.

Reads the per-conversation JSON files in ``examples/generated/`` plus the
manifest and summary, and writes ``examples/REPORT.md`` — a reviewer-friendly
overview that doesn't require opening 60 JSON files.

What's in the report:

  * headline metrics (n conversations, n total scores, mean confidence,
    aggregate latency, model + embedder used)
  * stratification table (tag distribution)
  * score distribution by category (text histogram)
  * top-3 facets per conversation, ranked by score
  * 8 random conversations spotlit with their full top-3 + rationales
  * known-limitations callout (cross-references DESIGN_DECISIONS.md)

Run:
    PYTHONPATH=. python scripts/build_report.py

Output:
    examples/REPORT.md
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED = REPO_ROOT / "examples" / "generated"
MANIFEST = REPO_ROOT / "examples" / "manifest.csv"
SUMMARY = REPO_ROOT / "examples" / "summary.json"
OUT = REPO_ROOT / "examples" / "REPORT.md"
ENRICHED = REPO_ROOT / "data" / "processed" / "facets_enriched.jsonl"


def _load_facet_categories() -> dict[str, str]:
    cats: dict[str, str] = {}
    if not ENRICHED.exists():
        return cats
    with ENRICHED.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            cats[obj["facet_id"]] = obj["category"]
    return cats


def _text_histogram(counts: dict, *, width: int = 40) -> list[str]:
    if not counts:
        return ["(no data)"]
    max_v = max(counts.values()) or 1
    rows = []
    for k in sorted(counts.keys(), key=lambda x: (-counts[x], str(x))):
        bar = "█" * max(1, int(round((counts[k] / max_v) * width)))
        rows.append(f"  {str(k):>22}  {bar} {counts[k]}")
    return rows


def main() -> int:
    if not GENERATED.exists() or not list(GENERATED.glob("*.json")):
        print("error: examples/generated/ is empty. run `make examples` first.")
        return 1

    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    cats = _load_facet_categories()

    convs = []
    for p in sorted(GENERATED.glob("*.json")):
        try:
            convs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue

    if not convs:
        print("error: no scored conversations parsed.")
        return 1

    n_conv = len(convs)
    all_scores = [s for c in convs for ts in c["turn_scores"] for s in ts["scores"]]
    n_scores = len(all_scores)
    mean_conf = mean(s["confidence"] for s in all_scores) if all_scores else 0.0
    elapsed_total = sum(c["pipeline_meta"].get("elapsed_seconds", 0) for c in convs)
    backend = convs[0]["pipeline_meta"].get("client", "unknown")
    embedder = convs[0]["pipeline_meta"].get("embedder", "unknown")
    n_facets = convs[0]["pipeline_meta"].get("n_facets_indexed", "?")
    top_k = convs[0]["pipeline_meta"].get("top_k", "?")

    score_dist = Counter(s["score"] for s in all_scores)

    # Score distribution by category
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for s in all_scores:
        cat = cats.get(s["facet_id"], "other")
        by_cat[cat][s["score"]] += 1

    # Top facets across the corpus
    facet_score_avg: dict[str, list[int]] = defaultdict(list)
    for s in all_scores:
        facet_score_avg[s["facet_name"]].append(s["score"])
    top_corpus_facets = sorted(
        ((name, mean(v), len(v)) for name, v in facet_score_avg.items() if len(v) >= 3),
        key=lambda r: -r[1],
    )[:15]

    # Spotlight — 8 random conversations
    rng = random.Random(42)
    spotlight = rng.sample(convs, min(8, n_conv))

    # Tag distribution
    tag_counts: Counter = Counter()
    for c in convs:
        for t in c.get("tags", []):
            tag_counts[t] += 1

    # ----------------------------------------------------------------- write
    lines: list[str] = []
    lines.append(f"# Ocean Across — Bulk Eval Report")
    lines.append("")
    lines.append(f"_Auto-generated from `examples/generated/` by `scripts/build_report.py`._")
    lines.append("")

    # Headline metrics
    lines.append("## Headline metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"| --- | --- |")
    lines.append(f"| Conversations scored | {n_conv} |")
    lines.append(f"| Total facet scores | {n_scores:,} |")
    lines.append(f"| Mean confidence | {mean_conf:.3f} |")
    lines.append(f"| Total LLM-eval time | {elapsed_total:.1f}s ({elapsed_total/60:.1f} min) |")
    lines.append(f"| LLM backend | `{backend}` |")
    lines.append(f"| Embedder | `{embedder}` |")
    lines.append(f"| Facets indexed | {n_facets} |")
    lines.append(f"| Top-K per turn | {top_k} |")
    lines.append("")

    # Score distribution
    lines.append("## Overall score distribution (1..5)")
    lines.append("")
    lines.append("```")
    lines.extend(_text_histogram({str(k): score_dist.get(k, 0) for k in (1, 2, 3, 4, 5)}))
    lines.append("```")
    lines.append("")

    # Per-category
    lines.append("## Score distribution by facet category")
    lines.append("")
    for cat in sorted(by_cat.keys()):
        c = by_cat[cat]
        total_in_cat = sum(c.values())
        lines.append(f"### `{cat}` ({total_in_cat:,} scores)")
        lines.append("")
        lines.append("```")
        lines.extend(_text_histogram({str(k): c.get(k, 0) for k in (1, 2, 3, 4, 5)}))
        lines.append("```")
        lines.append("")

    # Tag distribution
    lines.append("## Conversation stratification (by tag)")
    lines.append("")
    lines.append("```")
    lines.extend(_text_histogram(tag_counts))
    lines.append("```")
    lines.append("")

    # Top corpus-wide facets
    lines.append("## Top facets across corpus (mean score, n ≥ 3 observations)")
    lines.append("")
    lines.append("| Facet | Mean | N |")
    lines.append("| --- | ---: | ---: |")
    for name, m, n in top_corpus_facets:
        lines.append(f"| {name} | {m:.2f} | {n} |")
    lines.append("")

    # Spotlight conversations
    lines.append("## Spotlight: 8 random conversations")
    lines.append("")
    lines.append("Each block shows the top 3 facets by score for each turn,")
    lines.append("with the model's rationale. Useful for spot-checking quality.")
    lines.append("")
    for c in spotlight:
        cid = c["conversation_id"]
        title = c.get("title", "")
        tags = ", ".join(c.get("tags", []))
        lines.append(f"### `{cid}` — {title}")
        lines.append(f"_tags: {tags}_")
        lines.append("")
        for ts in c["turn_scores"]:
            spk = ts["speaker"]
            txt = ts["text"]
            lines.append(f"**Turn {ts['turn_index']} [{spk}]:**  _{txt[:160]}_")
            top3 = sorted(ts["scores"], key=lambda s: -s["score"])[:3]
            for s in top3:
                rat = s.get("rationale") or "(no rationale)"
                lines.append(f"- **{s['facet_name']}** — score {s['score']}, conf {s['confidence']:.2f}")
                lines.append(f"  _{rat[:160]}_")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Known limitations
    lines.append("## Known limitations")
    lines.append("")
    lines.append(
        "Documented in detail in [`docs/DESIGN_DECISIONS.md`](../docs/DESIGN_DECISIONS.md), "
        "specifically sections 11-14. Summary:"
    )
    lines.append("")
    lines.append(
        "- The scorer is intentionally conservative on speaker-vs-described "
        "disambiguation — assistant turns that *acknowledge* a user's emotion "
        "are correctly NOT attributed that emotion, but the model sometimes "
        "over-corrects and underscores facets the assistant *is* delivering "
        "(e.g. real Compassion in an empathic reply)."
    )
    lines.append(
        "- Retrieval at `top_k=20` can miss a semantically relevant facet when "
        "the turn describes a state without naming the facet. Mitigation: "
        "raise top_k or add hybrid (BM25 + dense) retrieval."
    )
    lines.append(
        "- Confidence in this report is pseudo-calibrated. For real per-prediction "
        "calibration, run `scripts/run_calibration_appendix.py`."
    )
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
