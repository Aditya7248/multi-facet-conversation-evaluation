"""Streamlit UI for the multi-facet conversation evaluator.

The UI is one Python file because it needs to be (a) demoable in 10
seconds by a reviewer, (b) easy to dockerize, (c) easy to deploy to
Hugging Face Spaces or Streamlit Community Cloud as the optional
"deployed URL" deliverable.

It calls the FastAPI service at ``$API_URL`` (default
http://localhost:8080), so you can run it standalone or via
``docker compose up``. The same UI works against any backend the
``LLMClient`` factory selects — Ollama, vLLM, HF, or the heuristic
fallback.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8080")


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Ocean Across — Conversation Evaluator",
    page_icon="🌊",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp { background: #0e1117; }
      .metric-card { padding: 1rem; border-radius: 8px; background: #1c2230; }
      .small-muted { color: #98a2b3; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=300.0)


def get_health() -> dict:
    try:
        return _client().get("/health").json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


def call_score(payload: dict) -> dict:
    r = _client().post("/score", json=payload)
    r.raise_for_status()
    return r.json()


def call_retrieve(text: str, top_k: int, category: str | None) -> list[dict]:
    body = {"text": text, "top_k": top_k}
    if category and category != "all":
        body["category"] = category
    r = _client().post("/retrieve", json=body)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Sidebar — backend health + controls
# ---------------------------------------------------------------------------


with st.sidebar:
    st.title("🌊  Ocean Across")
    st.caption("Multi-facet conversation evaluation")
    health = get_health()
    if health.get("status") == "ok":
        st.success(f"Backend: `{health['backend']}`")
        st.metric("Facets indexed", health["n_facets"])
    else:
        st.error("API unreachable")
        st.code(health.get("error", "n/a"))

    st.divider()
    top_k = st.slider("Top-K facets per turn", 5, 200, value=health.get("default_top_k", 40), step=5,
                      help="The retriever picks this many facets to score per turn. The scaling lever.")
    category = st.selectbox(
        "Category filter",
        options=[
            "all",
            "linguistic_quality", "pragmatics", "safety", "emotion",
            "personality", "cognition_reasoning", "relational",
            "clinical_health", "behavioral_lifestyle",
            "spirituality_culture", "other",
        ],
        index=0,
    )

    st.divider()
    st.caption(f"API: `{API_URL}`")
    st.caption(f"Embedder: `{health.get('embedder', 'n/a')}`")


# ---------------------------------------------------------------------------
# Main panel — conversation editor
# ---------------------------------------------------------------------------


st.title("Score a conversation")
st.write(
    "Paste a single message or a multi-turn conversation. "
    "For multi-turn, prefix each line with `user:` or `assistant:`. "
    "Bare text is treated as a single user turn."
)

DEFAULT_CONV = """user: I've been working with terminally ill patients for fifteen years and I don't feel anything anymore when they pass.
assistant: That sounds like compassion fatigue — a real, treatable condition. Reaching out is a healthy first step. Would it help to talk through what your weeks look like?
user: I just feel like a fraud showing up to work.
assistant: You're not a fraud. Burnout in palliative care is documented and well-studied; it doesn't undo years of meaningful work."""


col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    raw = st.text_area("Conversation", value=DEFAULT_CONV, height=320, label_visibility="collapsed")
    submit = st.button("Score conversation", type="primary", width="stretch")

# Title and tags are metadata only — they don't influence scoring. Set silently
# so the conversation downloads have a sensible filename / labels.
title = "UI test"
tags_str = ""


def _preview_text(text: str) -> str:
    """Pick the first non-empty line from `text`, stripping any `speaker:` prefix.
    Robust to leading/trailing whitespace, blank lines, and missing prefixes."""
    if not text or not text.strip():
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            head, _, tail = line.partition(":")
            if head.strip().lower() in {"user", "assistant", "system"}:
                line = tail.strip()
        return line
    return ""


with col_right:
    st.subheader("Top-K retrieval preview")
    preview_text = _preview_text(raw)
    if not preview_text:
        st.info("Paste a conversation on the left to preview which facets the retriever will pick.")
    else:
        st.caption(f"Showing top {min(top_k, 25)} retrieved facets for the first turn.")
        try:
            hits = call_retrieve(preview_text, top_k=min(top_k, 25), category=category)
            if not hits:
                st.warning("No facets retrieved — try a longer conversation.")
            else:
                df_hits = pd.DataFrame(hits)
                cols = [c for c in ["rank", "name", "category", "score"] if c in df_hits.columns]
                df_show = df_hits[cols].rename(columns={"score": "similarity"})
                # Display rank 1-indexed for humans (API stays 0-indexed for callers).
                if "rank" in df_show.columns:
                    df_show["rank"] = df_show["rank"] + 1
                # Size the table to its actual rows so we don't show empty padding.
                # Streamlit dataframe: header ≈ 38 px, each row ≈ 35 px.
                table_h = min(500, 38 + 35 * len(df_show) + 4)
                st.dataframe(df_show, hide_index=True, width="stretch", height=table_h)
        except Exception as e:
            st.error(f"retrieve failed: {e}")


# ---------------------------------------------------------------------------
# Score + render
# ---------------------------------------------------------------------------


def _parse_conversation(text: str) -> dict:
    """Parse the textarea content into structured turns.

    Forgiving rules:
      * Lines starting with `user:`, `assistant:`, or `system:` are parsed as
        explicit speaker turns (multi-turn flow).
      * If NO line has a recognised speaker prefix, the entire input is
        treated as a single `user:` turn — so a reviewer can just paste a
        bare message and have it work.
    """
    lines = [t for t in text.splitlines() if t.strip()]
    turns = []

    for line in lines:
        if ":" not in line:
            continue
        spk, content = line.split(":", 1)
        spk = spk.strip().lower()
        if spk not in {"user", "assistant", "system"}:
            continue
        turns.append({"turn_index": len(turns), "speaker": spk, "text": content.strip()})

    # Fallback: no explicit speaker prefixes — treat the whole blob as one user turn.
    if not turns and text.strip():
        turns.append({"turn_index": 0, "speaker": "user", "text": text.strip()})

    return {
        "conversation_id": "ui-adhoc",
        "title": title,
        "tags": [t.strip() for t in tags_str.split(",") if t.strip()],
        "turns": turns,
    }


if submit:
    conv = _parse_conversation(raw)
    if not conv["turns"]:
        st.error("No valid turns parsed. Format: `user: ...` or `assistant: ...`")
        st.stop()

    body = {"conversation": conv, "top_k": top_k}
    if category != "all":
        body["category"] = category

    with st.spinner("Routing to facets and scoring…"):
        try:
            result = call_score(body)
        except Exception as e:
            st.error(f"score failed: {e}")
            st.stop()

    # ---- summary cards -----------------------------------------------------
    summary = result["summary"]
    meta = result["pipeline_meta"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Turns", summary["n_turns"])
    c2.metric("Facet scores", summary["n_facet_scores"])
    c3.metric("Avg confidence", f"{summary['avg_confidence']:.2f}")
    c4.metric("Latency (s)", meta["elapsed_seconds"])

    st.caption(
        f"Backend: `{meta['client']}`  ·  Embedder: `{meta['embedder']}`  ·  "
        f"Indexed facets: {meta['n_facets_indexed']}  ·  Top-K: {meta['top_k']}"
    )

    # ---- per-turn detail ---------------------------------------------------
    for ts in result["turn_scores"]:
        st.markdown(f"### Turn {ts['turn_index']} — `{ts['speaker']}`")
        st.write(ts["text"])

        scores = ts["scores"]
        if not scores:
            st.info("No facets retrieved for this turn.")
            continue

        df = pd.DataFrame(scores)[["facet_name", "score", "confidence", "rationale"]]
        df = df.sort_values("score", ascending=False).reset_index(drop=True)

        chart = (
            alt.Chart(df.head(20))
            .mark_bar()
            .encode(
                y=alt.Y("facet_name:N", sort="-x", title=None),
                x=alt.X("score:Q", scale=alt.Scale(domain=[0, 5]), title="Score"),
                color=alt.Color(
                    "confidence:Q",
                    scale=alt.Scale(scheme="viridis"),
                    legend=alt.Legend(title="Confidence"),
                ),
                tooltip=["facet_name", "score", "confidence", "rationale"],
            )
            .properties(height=400)
        )
        # `st.altair_chart` still uses the old `use_container_width` API in
        # Streamlit ≤1.50. Migration to `width=` only happened for dataframes
        # and buttons. Tolerating the deprecation warning here.
        st.altair_chart(chart, use_container_width=True)

        with st.expander("All scores (table)"):
            st.dataframe(df, hide_index=True, width="stretch")

    # ---- per-category aggregate -------------------------------------------
    st.markdown("### Category-level rollup")
    cat_means = defaultdict(list)
    facet_id_to_cat = {}
    facets_payload = _client().get("/facets", params={"page_size": 500}).json()
    for f in facets_payload.get("items", []):
        facet_id_to_cat[f["facet_id"]] = f["category"]
    # Page through if needed
    total = facets_payload["total"]
    page = 2
    while len(facet_id_to_cat) < total and page < 20:
        more = _client().get("/facets", params={"page": page, "page_size": 500}).json()
        for f in more.get("items", []):
            facet_id_to_cat[f["facet_id"]] = f["category"]
        page += 1

    for ts in result["turn_scores"]:
        for s in ts["scores"]:
            cat = facet_id_to_cat.get(s["facet_id"], "other")
            cat_means[cat].append(s["score"])
    cat_df = pd.DataFrame(
        [{"category": c, "mean_score": sum(v) / len(v), "n": len(v)} for c, v in cat_means.items()]
    ).sort_values("mean_score", ascending=False)
    if not cat_df.empty:
        st.bar_chart(cat_df.set_index("category")["mean_score"])
        st.dataframe(cat_df, hide_index=True, width="stretch")

    # ---- raw JSON download -------------------------------------------------
    st.download_button(
        "Download raw JSON",
        data=json.dumps(result, indent=2),
        file_name=f"{result['conversation_id']}_scores.json",
        mime="application/json",
    )
