"""Stage-1 router: pick the top-K facets relevant to a turn.

This is the lever that lets the architecture scale to 5000+ facets. We
embed the conversation turn and retrieve only the K most relevant
facet definitions; downstream the LLM scorer sees those K, never the
full list. K stays constant as the catalogue grows.

The retriever supports two modes:

  * ``retrieve(turn_text, top_k)``   pure embedding similarity
  * ``retrieve(turn_text, top_k, category=...)``   filter to a category

When ``category`` is provided the retriever fetches a wider window
(``top_k * 4``) and then filters — this preserves recall when the user
restricts to e.g. all SAFETY facets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from src.utils.config import load_config
from src.utils.embeddings import build_embedder, faiss_search, load_index
from src.utils.logging import get_logger
from src.utils.types import FacetCategory, FacetDefinition

log = get_logger(__name__)


@dataclass
class RetrievedFacet:
    facet: FacetDefinition
    score: float           # similarity in [-1, 1]
    rank: int              # 0-based among the returned hits


class FacetRetriever:
    """Loads the FAISS / numpy index and the enriched facet metadata."""

    def __init__(
        self,
        enriched_jsonl: Path,
        index_path: Path,
        meta_path: Path,
        embedder_name: str,
    ):
        self.embedder = build_embedder(embedder_name)
        self.index = load_index(index_path)
        with meta_path.open("r", encoding="utf-8") as fh:
            self.meta = json.load(fh)

        self.facets: list[FacetDefinition] = []
        self._by_id: dict[str, FacetDefinition] = {}
        with enriched_jsonl.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = FacetDefinition.model_validate_json(line)
                self.facets.append(d)
                self._by_id[d.facet_id] = d

        if len(self.facets) != self.meta["n_facets"]:
            raise RuntimeError(
                f"Index/metadata size mismatch: {self.meta['n_facets']} indexed vs {len(self.facets)} loaded"
            )
        log.info("Retriever loaded: %d facets, dim=%d", len(self.facets), self.meta["dim"])

    # ---- Public API ----------------------------------------------------

    def all_facets(self) -> list[FacetDefinition]:
        return list(self.facets)

    def by_id(self, facet_id: str) -> FacetDefinition:
        return self._by_id[facet_id]

    def retrieve(
        self,
        turn_text: str,
        top_k: int = 40,
        category: Optional[FacetCategory] = None,
        min_score: float = 0.0,
    ) -> list[RetrievedFacet]:
        if not turn_text.strip():
            return []

        if category is not None:
            wide = self._search(turn_text, top_k=top_k * 4)
            filtered = [r for r in wide if r.facet.category == category][:top_k]
            return [r for r in filtered if r.score >= min_score]

        return [r for r in self._search(turn_text, top_k=top_k) if r.score >= min_score]

    # ---- internals -----------------------------------------------------

    def _search(self, turn_text: str, top_k: int) -> list[RetrievedFacet]:
        qvec = self.embedder.encode([turn_text]).astype(np.float32)
        hits = faiss_search(self.index, qvec, top_k)[0]
        out: list[RetrievedFacet] = []
        for rank, h in enumerate(hits):
            if h.row < 0 or h.row >= len(self.facets):
                continue
            out.append(RetrievedFacet(facet=self.facets[h.row], score=h.score, rank=rank))
        return out


# ---------------------------------------------------------------------------
# Default builder
# ---------------------------------------------------------------------------


def build_default_retriever() -> FacetRetriever:
    cfg = load_config()
    return FacetRetriever(
        enriched_jsonl=Path(cfg["paths"]["enriched_jsonl"]),
        index_path=Path(cfg["paths"]["faiss_index"]),
        meta_path=Path(cfg["paths"]["faiss_meta"]),
        embedder_name=cfg["embedding"]["model"],
    )
