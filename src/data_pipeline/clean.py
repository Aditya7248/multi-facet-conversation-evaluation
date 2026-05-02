"""Step 1: clean the raw facets CSV.

Reads ``configs.paths.raw_facets`` and writes ``configs.paths.cleaned_facets``.

Cleaning operations applied (in order):

  1. Strip BOM / non-breaking spaces / surrounding whitespace.
  2. Drop the literal header row "Facets".
  3. Remove numbered prefixes such as "793. ".
  4. Strip trailing punctuation (':', ';', ',') so 'Democratic Leadership:' -> 'Democratic Leadership'.
  5. Split CamelCase like 'HonestyHumility' -> 'Honesty Humility'.
  6. Collapse internal whitespace.
  7. Drop empty / single-character rows.
  8. Deduplicate case-insensitively, keeping the first occurrence.
  9. Emit a stable ``facet_id`` (slug) for every row.

The output schema is:  ``facet_id, name, raw_name``

Everything else (category, rubric, exemplars) is added by ``enrich.py`` —
this module is intentionally LLM-free so it runs in any environment.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from src.utils.config import REPO_ROOT, load_config
from src.utils.logging import get_logger
from src.utils.text import normalize_facet_name, slugify

log = get_logger(__name__)


def clean_facets(raw_path: Path, out_path: Path) -> dict:
    """Run the cleaning pipeline. Returns a small stats dict."""
    raw_rows: list[str] = []
    with raw_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                continue
            raw_rows.append(row[0])

    # Drop the header row if present (some CSV exports embed it; ours has it).
    if raw_rows and raw_rows[0].strip().lower() in {"facets", "facet"}:
        raw_rows = raw_rows[1:]

    seen: set[str] = set()
    cleaned: list[tuple[str, str, str]] = []   # (facet_id, name, raw_name)
    dropped_empty = 0
    dropped_dup = 0

    for raw in raw_rows:
        normalized = normalize_facet_name(raw)
        if len(normalized) < 2:
            dropped_empty += 1
            continue
        key = normalized.lower()
        if key in seen:
            dropped_dup += 1
            continue
        seen.add(key)
        cleaned.append((slugify(normalized), normalized, raw.strip()))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["facet_id", "name", "raw_name"])
        writer.writerows(cleaned)

    stats = {
        "input_rows": len(raw_rows),
        "kept_rows": len(cleaned),
        "dropped_empty": dropped_empty,
        "dropped_duplicates": dropped_dup,
        "output_path": str(out_path),
    }
    log.info("[bold green]Cleaned facets[/]  %s", stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw facet CSV.")
    parser.add_argument("--raw", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config()
    raw_path = args.raw or Path(cfg["paths"]["raw_facets"])
    out_path = args.out or Path(cfg["paths"]["cleaned_facets"])

    if not raw_path.exists():
        # Fall back to copying from repo root if user dropped the CSV there
        alt = REPO_ROOT / "Facets Assignment.csv"
        if alt.exists():
            raw_path = alt
        else:
            raise FileNotFoundError(f"Raw facets CSV not found at {raw_path}")

    clean_facets(raw_path, out_path)


if __name__ == "__main__":
    main()
