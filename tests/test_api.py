"""HTTP surface tests using FastAPI's TestClient — no real network."""

from __future__ import annotations

from pathlib import Path

import pytest


def _has_artefacts() -> bool:
    return (Path("data/index/facets.npy").exists()
            or Path("data/index/facets.faiss").exists())


@pytest.fixture(scope="module")
def client():
    if not _has_artefacts():
        pytest.skip("run `make data-all` first")
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("fastapi[testclient] not installed")
    from src.api.server import app
    return TestClient(app)


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["n_facets"] > 0


def test_list_facets(client) -> None:
    r = client.get("/facets", params={"page_size": 25})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    assert len(body["items"]) <= 25
    assert "facet_id" in body["items"][0]


def test_retrieve_endpoint(client) -> None:
    r = client.post(
        "/retrieve",
        json={"text": "I am exhausted and burned out.", "top_k": 5},
    )
    assert r.status_code == 200
    items = r.json()
    assert 0 < len(items) <= 5
    assert items[0]["rank"] == 0


def test_score_endpoint(client) -> None:
    payload = {
        "conversation": {
            "conversation_id": "api-test",
            "title": "test",
            "tags": [],
            "turns": [
                {"turn_index": 0, "speaker": "user", "text": "I'm livid right now."},
            ],
        },
        "top_k": 6,
    }
    r = client.post("/score", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"] == "api-test"
    assert len(body["turn_scores"]) == 1
    assert body["turn_scores"][0]["scores"]
