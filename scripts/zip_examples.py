"""Build the examples ZIP without bundling __pycache__ or stray files."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EX = REPO_ROOT / "examples"
OUT = EX / "conversations_scored.zip"

INCLUDE = [
    "generated",
    "manifest.csv",
    "summary.json",
    "README.md",
    "REPORT.md",
    "conversations_table.md",
    "conversations_table.csv",
    "calibration_appendix",
]


def main() -> int:
    if OUT.exists():
        try:
            OUT.unlink()
        except OSError:
            print(f"warn: couldn't remove existing {OUT}; will write to a sibling.")
    target = OUT if not OUT.exists() else EX / "conversations_scored.new.zip"

    if not (EX / "generated").exists():
        print("error: examples/generated/ doesn't exist — run `make examples` first.")
        return 1

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            p = EX / item
            if p.is_dir():
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if not d.startswith(("__", "."))]
                    for f in files:
                        full = Path(root) / f
                        z.write(full, full.relative_to(EX))
            elif p.exists():
                z.write(p, item)

    n_entries = len(zipfile.ZipFile(target).namelist())
    print(f"wrote {target.relative_to(REPO_ROOT)} ({n_entries} entries, {target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
