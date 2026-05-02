"""Build per-conversation audit tables for reviewers — both Markdown and CSV.

Reads ``examples/generated/*.json`` and writes two artefacts in a single pass:

  * ``examples/conversations_table.md``  — narrative view: one section per
    conversation showing the actual turn text alongside a Markdown table of
    the top-N facet scores for that turn. Best for human reading.

  * ``examples/conversations_table.csv`` — flat tabular view: one row per
    (conversation, turn, facet) score. Best for filtering / pivoting in
    Excel or VS Code's CSV viewer. Columns:
        cid, title, tags, turn_index, speaker, turn_text, facet_id,
        facet_name, category, score, confidence, rationale, evidence_span

Complements:
  * ``examples/manifest.csv``    — metadata-only (counts, IDs, latency)
  * ``examples/REPORT.md``       — aggregate stats + 8 spotlights
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED = REPO_ROOT / "examples" / "generated"
ENRICHED = REPO_ROOT / "data" / "processed" / "facets_enriched.jsonl"
OUT_MD = REPO_ROOT / "examples" / "conversations_table.md"
OUT_CSV = REPO_ROOT / "examples" / "conversations_table.csv"

TOP_N_PER_TURN = 8           # how many top facets to show per turn
RATIONALE_LIMIT = 130        # chars
TEXT_LIMIT = 600             # chars of turn text shown


def _truncate(s: str | None, limit: int) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _md_escape(s: str) -> str:
    """Minimal escaping so pipes and backticks in rationales don't break tables."""
    return s.replace("|", "\\|").replace("\n", " ")


def _conf_dot(conf: float) -> str:
    """Visual confidence indicator in a single character."""
    if conf >= 0.7:
        return "●●●"
    if conf >= 0.55:
        return "●●○"
    if conf >= 0.4:
        return "●○○"
    return "○○○"


def _render_turn_table(scores: list[dict]) -> list[str]:
    """Top-N facets for a single turn, sorted by score desc, conf desc."""
    if not scores:
        return ["_(no facets retrieved for this turn)_", ""]
    ranked = sorted(scores, key=lambda s: (-s["score"], -s["confidence"]))[:TOP_N_PER_TURN]
    rows = [
        "| # | Facet | Score | Conf | Rationale |",
        "| --- | --- | :-: | :-: | --- |",
    ]
    for i, s in enumerate(ranked, 1):
        rows.append(
            f"| {i} | {_md_escape(s['facet_name'])} | **{s['score']}** | "
            f"{_conf_dot(s['confidence'])} {s['confidence']:.2f} | "
            f"{_md_escape(_truncate(s.get('rationale', ''), RATIONALE_LIMIT))} |"
        )
    rows.append("")
    return rows


def _render_conversation(conv: dict) -> list[str]:
    cid = conv["conversation_id"]
    title = conv.get("title") or ""
    tags = conv.get("tags") or []
    summary = conv.get("summary") or {}
    meta = conv.get("pipeline_meta") or {}

    lines: list[str] = []
    lines.append(f"### `{cid}` — {_md_escape(title)}")
    lines.append("")
    lines.append(f"**Tags:** {', '.join(f'`{t}`' for t in tags) or '_none_'}")
    lines.append(
        f"**Coverage:** {summary.get('n_facet_scores', 0)} facet scores  "
        f"·  **Avg confidence:** {summary.get('avg_confidence', 0.0):.2f}  "
        f"·  **Latency:** {meta.get('elapsed_seconds', 0):.1f}s"
    )
    lines.append("")

    for ts in conv["turn_scores"]:
        spk = ts["speaker"]
        idx = ts["turn_index"]
        text = _truncate(ts["text"], TEXT_LIMIT)
        lines.append(f"**Turn {idx} — `{spk}`:**")
        lines.append("")
        lines.append(f"> {_md_escape(text)}")
        lines.append("")
        lines.extend(_render_turn_table(ts.get("scores", [])))

    lines.append("---")
    lines.append("")
    return lines


def _load_facet_categories() -> dict[str, str]:
    """Map facet_id -> category from the enriched facet definitions."""
    cats: dict[str, str] = {}
    if not ENRICHED.exists():
        return cats
    with ENRICHED.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            cats[obj["facet_id"]] = obj["category"]
    return cats


def _write_csv(convs: list[dict], facet_cats: dict[str, str]) -> int:
    """Write the flat CSV: one row per (conversation, turn, facet score)."""
    fields = [
        "cid", "title", "tags", "turn_index", "speaker", "turn_text",
        "facet_id", "facet_name", "category",
        "score", "confidence", "rationale", "evidence_span",
    ]
    n_rows = 0
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for c in convs:
            cid = c["conversation_id"]
            title = c.get("title") or ""
            tags = "; ".join(c.get("tags") or [])
            for ts in c["turn_scores"]:
                turn_idx = ts["turn_index"]
                speaker = ts["speaker"]
                turn_text = ts["text"]
                for s in ts.get("scores", []):
                    w.writerow({
                        "cid": cid,
                        "title": title,
                        "tags": tags,
                        "turn_index": turn_idx,
                        "speaker": speaker,
                        "turn_text": turn_text,
                        "facet_id": s["facet_id"],
                        "facet_name": s["facet_name"],
                        "category": facet_cats.get(s["facet_id"], ""),
                        "score": s["score"],
                        "confidence": round(float(s["confidence"]), 4),
                        "rationale": s.get("rationale", "") or "",
                        "evidence_span": s.get("evidence_span", "") or "",
                    })
                    n_rows += 1
    return n_rows


def main() -> int:
    if not GENERATED.exists() or not list(GENERATED.glob("*.json")):
        print("error: examples/generated/ is empty. run `make examples` first.")
        return 1

    convs: list[dict] = []
    for p in sorted(GENERATED.glob("*.json")):
        try:
            convs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"warn: skipping {p.name}: {e}")

    facet_cats = _load_facet_categories()

    # Headline at the top of the document
    n_conv = len(convs)
    n_turns = sum(len(c["turn_scores"]) for c in convs)
    n_scores = sum(len(t["scores"]) for c in convs for t in c["turn_scores"])
    avg_conf = mean(
        s["confidence"] for c in convs for t in c["turn_scores"] for s in t["scores"]
    ) if n_scores else 0.0
    backend = convs[0]["pipeline_meta"].get("client", "unknown") if convs else "unknown"

    out_lines: list[str] = []
    out_lines.append("# Ocean Across — Per-Conversation Audit Table")
    out_lines.append("")
    out_lines.append(
        "_Auto-generated. One section per conversation, each showing the actual "
        "turn text alongside a table of the top-8 facet scores for that turn._"
    )
    out_lines.append("")
    out_lines.append(
        f"**{n_conv} conversations · {n_turns} turns · {n_scores:,} facet scores · "
        f"mean confidence {avg_conf:.3f} · backend `{backend}`**"
    )
    out_lines.append("")
    out_lines.append("Confidence dots: `●●●` ≥ 0.70  ·  `●●○` ≥ 0.55  ·  `●○○` ≥ 0.40  ·  `○○○` < 0.40")
    out_lines.append("")

    # Index
    out_lines.append("## Index")
    out_lines.append("")
    for c in convs:
        cid = c["conversation_id"]
        title = c.get("title") or ""
        tags = ", ".join(c.get("tags") or [])
        out_lines.append(f"- [`{cid}` — {title}](#{cid.lower()}--{title.lower().replace(' ', '-').replace(':', '').replace(',', '').replace('—', '').replace('—', '').replace('--', '-').strip('-')}) · _{tags}_")
    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")

    # Body — one section per conversation
    for c in convs:
        out_lines.extend(_render_conversation(c))

    OUT_MD.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(REPO_ROOT)} ({OUT_MD.stat().st_size:,} bytes, {n_conv} conversations)")

    # Flat CSV — one row per (convo, turn, facet)
    n_rows = _write_csv(convs, facet_cats)
    print(f"wrote {OUT_CSV.relative_to(REPO_ROOT)} ({OUT_CSV.stat().st_size:,} bytes, {n_rows:,} rows)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
