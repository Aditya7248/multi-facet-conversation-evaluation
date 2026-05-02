"""Step 3: build the FAISS facet-routing index.

Architecture role: this is the lever that lets the system handle 5000+
facets without redesign. Instead of asking the LLM to consider every
facet for every turn, we embed each facet's enriched text and, at
inference time, embed the conversation turn and retrieve only the top-K
relevant facets to score. K stays constant as the facet set grows.

Index choice: ``IndexFlatIP`` over L2-normalised vectors (= cosine
similarity), built in-memory and serialised to disk. For 5k facets this
is < 5 MB and sub-millisecond per query — switching to HNSW or IVF only
becomes worthwhile north of ~100k facets, which we don't expect.

Outputs:
    data/index/facets.faiss
    data/index/facets_meta.json   (ordered list of facet_ids matching index rows)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.utils.config import load_config
from src.utils.logging import get_logger
from src.utils.types import FacetDefinition

log = get_logger(__name__)


def _load_enriched(path: Path) -> list[FacetDefinition]:
    defs: list[FacetDefinition] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            defs.append(FacetDefinition.model_validate_json(line))
    return defs


def build_index(
    enriched_jsonl: Path,
    out_index: Path,
    out_meta: Path,
    embedder_name: str,
) -> dict:
    from src.utils.embeddings import build_embedder, save_index
    from src.utils.embeddings import build_index as build_vec_index

    defs = _load_enriched(enriched_jsonl)
    log.info("Embedding %d facets with %s", len(defs), embedder_name)

    embedder = build_embedder(embedder_name)
    texts = [d.embed_text() for d in defs]
    vecs = embedder.encode(texts).astype(np.float32)

    dim = vecs.shape[1]
    index = build_vec_index(vecs)
    save_index(index, out_index)

    meta = {
        "embedder": embedder_name,
        "dim": int(dim),
        "n_facets": len(defs),
        "facet_ids": [d.facet_id for d in defs],
        "facet_names": [d.name for d in defs],
        "facet_categories": [d.category.value for d in defs],
    }
    with out_meta.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    log.info("[bold green]Built FAISS index[/]  dim=%d n=%d → %s", dim, len(defs), out_index)
    return {"dim": dim, "n_facets": len(defs), "out_index": str(out_index), "out_meta": str(out_meta)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FAISS facet-routing index.")
    parser.add_argument("--enriched", type=Path, default=None)
    parser.add_argument("--out-index", type=Path, default=None)
    parser.add_argument("--out-meta", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config()
    enriched = args.enriched or Path(cfg["paths"]["enriched_jsonl"])
    out_index = args.out_index or Path(cfg["paths"]["faiss_index"])
    out_meta = args.out_meta or Path(cfg["paths"]["faiss_meta"])
    embedder = cfg["embedding"]["model"]

    if not enriched.exists():
        raise FileNotFoundError(
            f"Enriched facets not found at {enriched}. Run `make data-enrich` first."
        )

    build_index(enriched, out_index, out_meta, embedder)


if __name__ == "__main__":
    main()
