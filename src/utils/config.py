"""Config loader: YAML + environment overrides.

Loads `configs/config.yaml` and overlays values from environment variables
(or a `.env` file if `python-dotenv` is installed). Returns a frozen dict
so downstream code can rely on immutability.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "config.yaml"


def _coerce(value: str) -> Any:
    """Best-effort string -> int/float/bool/str."""
    low = value.strip().lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return value


_ENV_OVERRIDES = {
    "LLM_BACKEND": ("llm", "backend"),
    "OLLAMA_HOST": ("llm", "ollama_host"),
    "OLLAMA_MODEL": ("llm", "model"),
    "VLLM_BASE_URL": ("llm", "vllm_base_url"),
    "VLLM_MODEL": ("llm", "vllm_model"),
    "VLLM_API_KEY": ("llm", "vllm_api_key"),
    "HF_MODEL": ("llm", "hf_model"),
    "HF_DEVICE": ("llm", "hf_device"),
    "EMBED_MODEL": ("embedding", "model"),
    "RETRIEVE_TOP_K": ("retrieval", "top_k"),
    "SCORE_TEMPERATURE": ("llm", "temperature"),
    "SCORE_MAX_TOKENS": ("llm", "max_tokens"),
    "PARALLEL_SCORERS": ("scoring", "parallel_workers"),
    "API_PORT": ("api", "port"),
    "UI_PORT": ("ui", "port"),
}


def _set_nested(d: dict, path: tuple[str, ...], value: Any) -> None:
    cur = d
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    # Resolve repo-relative paths
    paths = cfg.get("paths", {})
    for k, v in list(paths.items()):
        if isinstance(v, str) and not Path(v).is_absolute():
            paths[k] = str(REPO_ROOT / v)
    cfg["paths"] = paths
    cfg["repo_root"] = str(REPO_ROOT)

    # Environment overlay
    for env_key, dotted in _ENV_OVERRIDES.items():
        if env_key in os.environ and os.environ[env_key].strip():
            _set_nested(cfg, dotted, _coerce(os.environ[env_key]))

    return cfg


def get_path(key: str) -> Path:
    cfg = load_config()
    return Path(cfg["paths"][key])
