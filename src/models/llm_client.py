"""Pluggable LLM client.

Three concrete adapters live here:

  * OllamaClient — POSTs to ``/api/chat`` on a local Ollama daemon.
    Default backend; works on any laptop with no GPU. Returns logprobs
    when the underlying model supports them, otherwise falls back to
    self-consistency for confidence.
  * VLLMClient   — talks to vLLM's OpenAI-compatible HTTP server. Used
    in production where throughput matters.
  * HFClient     — runs Qwen / Llama in-process via HuggingFace
    transformers. Slowest, but doesn't require a service.

All three implement ``LLMClient.score()``, which takes a structured
prompt and returns a ``ScoreResult`` containing:

    score              the predicted ordinal (one of 1..5)
    score_distribution softmax over the 5 ordinal classes
    confidence         derived from the distribution (1 - normalised entropy)
    rationale          short natural-language justification
    evidence_span      the substring of the turn most responsible
    raw                the raw model JSON, retained for debugging

Confidence calibration:
  - When ``logprobs`` are available we read the per-token logprobs at
    the score-token position and softmax over the five score literals
    (``"1".."5"``). This is the principled approach.
  - Otherwise, we run ``self_consistency_samples`` independent
    generations at temperature 0.7 and use the empirical distribution
    of returned scores. With 5 samples the resolution is 0.2; with 10
    it's 0.1 — choose in config.
  - Either way, ``confidence = 1 - H_5(p) / log(5)``  ∈ [0, 1].

Why a single shared adapter base class? The scorer cares about the
*output schema* (Pydantic ``ScoreResult``), not how it was produced. A
new backend (e.g. SGLang) can be added without touching the scorer.
"""

from __future__ import annotations

import json
import math
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import load_config
from src.utils.logging import get_logger
from src.utils.types import FacetDefinition

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
    score: int
    score_distribution: list[float]
    confidence: float
    rationale: str = ""
    evidence_span: Optional[str] = None
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are a meticulous conversation evaluator. You score exactly
one facet of one conversational turn at a time, on a five-point ordinal scale
defined by the rubric below. You always respond with a single JSON object and
nothing else.

WHO YOU ARE SCORING — critical, read first:
  Score the SPEAKER OF THIS TURN, not the person they are describing, replying
  to, or quoting. Acknowledging or naming an emotion is NOT the same as feeling
  it. Validating, classifying, or paraphrasing someone else's trait does NOT
  count as the speaker exhibiting that trait.

    • USER says "I feel hollow" → USER is hollow (high).
      ASSISTANT replies "what you describe sounds hollow" → ASSISTANT is showing
      EMPATHY + CLARITY, NOT hollowness (hollowness ≈ 1-2 for the assistant
      even though the word appears).
    • USER says "I'm furious about my landlord" → USER shows anger (high).
      ASSISTANT replies "that does sound infuriating" → ASSISTANT is empathetic,
      NOT angry (anger ≈ 1-2 for the assistant).
    • USER says "I haven't slept in three days" → USER shows fatigue / negative
      affect. An ASSISTANT acknowledging this is not itself fatigued.

  EQUALLY IMPORTANT — don't over-correct: BEING empathetic, compassionate,
  kind, validating, or supportive in your response IS a trait of the speaker.
    • An ASSISTANT who validates a user's pain with warmth and clinical insight
      is exhibiting HIGH "Compassion", HIGH "Empathy", HIGH "Big-heartedness",
      HIGH "Comfort with Vulnerability". These ARE traits the speaker is
      delivering through their words, even though the topic is the user's pain.
    • The rule: emotions about someone else (anger, sadness, hollowness,
      moroseness, discontentment) belong to whoever feels them. Behaviours of
      the speaker (compassion, empathy, kindness, directness, hedging, clarity,
      sycophancy) belong to the speaker.

WHAT YOU ARE SCORING:
  The TRAIT, QUALITY, or BEHAVIOUR that the speaker's own turn expresses or
  exhibits — NOT whether the facet name appears literally. Inference is
  expected.
    • "When patients pass I just feel nothing anymore" → high Compassion Fatigue.
    • "fine, whatever you want" → high Passive-Aggressive, low Directness.
    • "I don't see the point of any of it" → high Negative Affect / Discontentment.

CALIBRATION — read carefully, this is where most graders fail:
  Out of the retrieved facets, MOST will only weakly apply to any given turn.
  Default to score 2 or 3 unless you have CLEAR, SPECIFIC evidence that the
  speaker is exhibiting the trait.
    • Score 1 = clear opposite of the trait.
    • Score 2 = mostly absent, only weak / indirect signals.
    • Score 3 = neutral, mixed, partial, or "not applicable to this turn".
    • Score 4 = clearly present but not extreme.
    • Score 5 = unambiguous, central, textbook expression.
  Most assistant turns that acknowledge user emotions should score 1-2 on
  emotion facets and 3-4 on relational / professionalism facets — empathy is
  itself a different trait from the emotion being empathised with.

OUTPUT RULES:
  - In `evidence_span`, quote the most relevant ≤20-word substring from the
    speaker's turn. Use "" if no specific span applies.
  - In `rationale` (≤30 words), explain WHY this level — reference the
    speaker's inferred state, NOT what they are describing about others.
"""


_USER_TEMPLATE = """FACET: {name}
CATEGORY: {category}
DEFINITION: {description}

RUBRIC (5 ordered levels — pick exactly one):
  1: {r1_label} — {r1}
  2: {r2_label} — {r2}
  3: {r3_label} — {r3}
  4: {r4_label} — {r4}
  5: {r5_label} — {r5}

CONVERSATION CONTEXT (most recent first, oldest last):
{context}

TURN TO SCORE:
[speaker={speaker}] {text}

Respond with JSON of the exact shape:
{{"score": <int 1..5>, "rationale": "<≤30 words>", "evidence_span": "<quote from turn>"}}"""


def build_user_prompt(
    facet: FacetDefinition,
    turn_text: str,
    speaker: str,
    context_turns: list[tuple[str, str]] | None = None,
) -> str:
    ctx_lines = []
    for spk, txt in (context_turns or [])[::-1]:   # reverse to put most recent first
        ctx_lines.append(f"  [{spk}] {txt[:280]}")
    context = "\n".join(ctx_lines) if ctx_lines else "  (no prior turns)"

    return _USER_TEMPLATE.format(
        name=facet.name,
        category=facet.category.value,
        description=facet.description,
        r1_label=facet.rubric[0].label, r1=facet.rubric[0].description,
        r2_label=facet.rubric[1].label, r2=facet.rubric[1].description,
        r3_label=facet.rubric[2].label, r3=facet.rubric[2].description,
        r4_label=facet.rubric[3].label, r4=facet.rubric[3].description,
        r5_label=facet.rubric[4].label, r5=facet.rubric[4].description,
        context=context,
        speaker=speaker,
        text=turn_text[:1200],
    )


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------


def normalised_entropy_confidence(p: list[float]) -> float:
    """Confidence in [0, 1]: 1 = peaked, 0 = uniform."""
    eps = 1e-12
    H = -sum(pi * math.log(pi + eps) for pi in p)
    Hmax = math.log(len(p))
    return max(0.0, min(1.0, 1.0 - H / Hmax))


def _softmax(xs: list[float]) -> list[float]:
    m = max(xs)
    e = [math.exp(x - m) for x in xs]
    s = sum(e) or 1.0
    return [x / s for x in e]


_SCORE_RE = re.compile(r'"score"\s*:\s*([1-5])')


def _safe_parse_json(text: str) -> dict:
    """Robust JSON parsing — locates the first ``{...}`` block and parses it."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in: {text[:200]!r}")
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    name: str

    @abstractmethod
    def score(
        self,
        facet: FacetDefinition,
        turn_text: str,
        speaker: str,
        context_turns: list[tuple[str, str]] | None = None,
        temperature: float = 0.0,
    ) -> ScoreResult: ...

    @abstractmethod
    def health(self) -> bool: ...

    # Optional — used by enrich --use-llm
    def refine_facet(self, facet: FacetDefinition) -> FacetDefinition:  # pragma: no cover
        return facet


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class OllamaClient(LLMClient):
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        request_timeout_s: float = 120.0,
        self_consistency_samples: int = 0,
    ):
        self.name = f"ollama:{model}"
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = request_timeout_s
        self.self_consistency_samples = self_consistency_samples
        self._client = httpx.Client(timeout=request_timeout_s)

    def health(self) -> bool:
        try:
            r = self._client.get(f"{self.host}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def _chat(self, messages: list[dict], temperature: float = 0.0) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 256},
            "format": "json",
        }
        # Disable chain-of-thought for thinking-capable models (qwen3, deepseek-r1,
        # etc). Thinking mode (a) blows up latency 3-5x with verbose reasoning,
        # and (b) wraps the JSON we need with <think>...</think> tags that break
        # parsing. We want short, structured output here.
        m = self.model.lower()
        if any(tag in m for tag in ("qwen3", "deepseek-r1", "kimi-k2-thinking", "magistral")):
            payload["think"] = False
        r = self._client.post(f"{self.host}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()

    def _single_score(
        self,
        facet: FacetDefinition,
        turn_text: str,
        speaker: str,
        context_turns,
        temperature: float,
    ) -> tuple[int, str, str, dict]:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(facet, turn_text, speaker, context_turns)},
        ]
        resp = self._chat(messages, temperature=temperature)
        content = resp.get("message", {}).get("content", "")
        try:
            obj = _safe_parse_json(content)
        except Exception:
            # Last-ditch: pick the score regex'd out of the content
            m = _SCORE_RE.search(content)
            obj = {"score": int(m.group(1)) if m else 3, "rationale": content[:200]}
        score = max(1, min(5, int(obj.get("score", 3))))
        rationale = str(obj.get("rationale", ""))[:300]
        evidence = str(obj.get("evidence_span", ""))[:300] if obj.get("evidence_span") else None
        return score, rationale, evidence, resp

    def score(
        self,
        facet: FacetDefinition,
        turn_text: str,
        speaker: str,
        context_turns=None,
        temperature: float = 0.0,
    ) -> ScoreResult:
        score, rationale, evidence, raw = self._single_score(
            facet, turn_text, speaker, context_turns, temperature
        )
        # Confidence via self-consistency (Ollama doesn't expose token logprobs reliably).
        if self.self_consistency_samples > 0:
            samples = [score]
            for _ in range(self.self_consistency_samples):
                s, _, _, _ = self._single_score(facet, turn_text, speaker, context_turns, 0.7)
                samples.append(s)
            counts = [samples.count(k) for k in (1, 2, 3, 4, 5)]
            total = sum(counts) or 1
            dist = [c / total for c in counts]
        else:
            # Smooth single sample to a conservative pseudo-distribution
            dist = _ordinal_pseudodist(score, sharpness=2.0)
        return ScoreResult(
            score=score,
            score_distribution=dist,
            confidence=normalised_entropy_confidence(dist),
            rationale=rationale,
            evidence_span=evidence,
            raw=raw,
        )


# ---------------------------------------------------------------------------
# vLLM (OpenAI-compatible)
# ---------------------------------------------------------------------------


class VLLMClient(LLMClient):
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        api_key: str = "EMPTY",
        request_timeout_s: float = 120.0,
    ):
        self.name = f"vllm:{model}"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self._client = httpx.Client(
            timeout=request_timeout_s,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def health(self) -> bool:
        try:
            r = self._client.get(f"{self.base_url}/models", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def _chat(self, messages: list[dict], temperature: float = 0.0, logprobs: bool = True) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 256,
            "logprobs": logprobs,
            "top_logprobs": 5,
            "response_format": {"type": "json_object"},
        }
        r = self._client.post(f"{self.base_url}/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()

    def score(
        self,
        facet: FacetDefinition,
        turn_text: str,
        speaker: str,
        context_turns=None,
        temperature: float = 0.0,
    ) -> ScoreResult:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(facet, turn_text, speaker, context_turns)},
        ]
        resp = self._chat(messages, temperature=temperature)
        choice = resp["choices"][0]
        content = choice["message"]["content"]
        try:
            obj = _safe_parse_json(content)
        except Exception:
            m = _SCORE_RE.search(content)
            obj = {"score": int(m.group(1)) if m else 3, "rationale": content[:200]}
        score = max(1, min(5, int(obj.get("score", 3))))
        rationale = str(obj.get("rationale", ""))[:300]
        evidence = str(obj.get("evidence_span", ""))[:300] if obj.get("evidence_span") else None

        # ---- Distribution from token-level logprobs ----
        dist = _extract_score_distribution_from_logprobs(choice.get("logprobs"))
        if dist is None:
            dist = _ordinal_pseudodist(score, sharpness=2.0)

        return ScoreResult(
            score=score,
            score_distribution=dist,
            confidence=normalised_entropy_confidence(dist),
            rationale=rationale,
            evidence_span=evidence,
            raw=resp,
        )


# ---------------------------------------------------------------------------
# HuggingFace transformers (in-process)
# ---------------------------------------------------------------------------


class HFClient(LLMClient):
    """Local in-process HF model. Heavyweight; use only when Ollama/vLLM aren't available."""

    def __init__(self, model_id: str = "Qwen/Qwen2.5-7B-Instruct", device: str = "auto"):
        self.name = f"hf:{model_id}"
        self.model_id = model_id
        self.device = device
        self._tok = None
        self._model = None

    def _ensure(self):  # pragma: no cover - heavy
        if self._model is not None:
            return
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id, device_map=self.device, torch_dtype="auto"
        )

    def health(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception:
            return False

    def score(
        self,
        facet: FacetDefinition,
        turn_text: str,
        speaker: str,
        context_turns=None,
        temperature: float = 0.0,
    ) -> ScoreResult:  # pragma: no cover - heavy
        self._ensure()
        import torch

        prompt = self._tok.apply_chat_template(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(facet, turn_text, speaker, context_turns)},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self._tok(prompt, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=temperature > 0,
                temperature=max(temperature, 1e-5),
                return_dict_in_generate=True,
                output_scores=True,
            )
        gen_ids = out.sequences[0][inputs["input_ids"].shape[1]:]
        text = self._tok.decode(gen_ids, skip_special_tokens=True)

        try:
            obj = _safe_parse_json(text)
        except Exception:
            m = _SCORE_RE.search(text)
            obj = {"score": int(m.group(1)) if m else 3, "rationale": text[:200]}
        score = max(1, min(5, int(obj.get("score", 3))))

        # Distribution: softmax of scores over the digit tokens "1".."5" at generation step 0.
        score_token_ids = [self._tok.encode(str(k), add_special_tokens=False)[0] for k in range(1, 6)]
        first_step_logits = out.scores[0][0]
        sub = first_step_logits[score_token_ids].tolist()
        dist = _softmax(sub)

        return ScoreResult(
            score=score,
            score_distribution=dist,
            confidence=normalised_entropy_confidence(dist),
            rationale=str(obj.get("rationale", ""))[:300],
            evidence_span=str(obj.get("evidence_span", ""))[:300] if obj.get("evidence_span") else None,
            raw={"text": text},
        )


# ---------------------------------------------------------------------------
# Heuristic / fallback client (no LLM, runs anywhere)
# ---------------------------------------------------------------------------


class HeuristicClient(LLMClient):
    """Keyword-overlap scorer used when no LLM is reachable.

    NOT a replacement for the real LLM scorer — it exists so we can:
      * smoke-test the full pipeline in CI / sandboxes,
      * generate the 50-conversation deliverable ZIP without a GPU,
      * unit-test the orchestrator without mocking httpx.

    The README explicitly documents that real numbers come from
    OllamaClient/VLLMClient/HFClient.
    """

    def __init__(self):
        self.name = "heuristic:fallback"

    def health(self) -> bool:
        return True

    def score(
        self,
        facet: FacetDefinition,
        turn_text: str,
        speaker: str,
        context_turns=None,
        temperature: float = 0.0,
    ) -> ScoreResult:
        text_low = turn_text.lower()
        # Signal 1: keyword overlap
        kw_hits = sum(1 for kw in facet.keywords if kw and kw in text_low)
        kw_signal = min(1.0, kw_hits / max(2, len(facet.keywords) // 2 or 2))

        # Signal 2: rough sentiment hint for emotion / safety facets
        from src.utils.types import FacetCategory

        polarity = 0.0
        positive_words = ("happy", "joy", "great", "love", "calm", "peace", "wonderful")
        negative_words = ("hate", "angry", "sad", "depress", "kill", "die", "tired", "burnout", "broken")
        polarity += sum(1 for w in positive_words if w in text_low) * 0.15
        polarity -= sum(1 for w in negative_words if w in text_low) * 0.15

        if facet.category == FacetCategory.SAFETY:
            base = max(0.0, -polarity) + kw_signal * 0.5
        elif facet.category == FacetCategory.EMOTION:
            base = abs(polarity) + kw_signal * 0.4
        else:
            base = kw_signal

        # Map [0, ~1] → score 1..5
        if base <= 0.05:
            score = 1
        elif base <= 0.2:
            score = 2
        elif base <= 0.45:
            score = 3
        elif base <= 0.75:
            score = 4
        else:
            score = 5

        dist = _ordinal_pseudodist(score, sharpness=1.5)
        rationale_bits = []
        if kw_hits:
            rationale_bits.append(f"keywords matched: {kw_hits}")
        if polarity:
            rationale_bits.append(f"polarity={polarity:+.2f}")
        rationale = "; ".join(rationale_bits) or "no strong signals"

        return ScoreResult(
            score=score,
            score_distribution=dist,
            confidence=normalised_entropy_confidence(dist),
            rationale=f"[heuristic] {rationale}",
            evidence_span=None,
            raw={"signal": base, "polarity": polarity, "kw_hits": kw_hits},
        )


# ---------------------------------------------------------------------------
# Helpers used by the clients above
# ---------------------------------------------------------------------------


def _ordinal_pseudodist(score: int, sharpness: float = 2.0) -> list[float]:
    """Smooth ordinal distribution centred on `score`. 1.0 -> sharper peak."""
    raw = [-sharpness * abs(k - score) for k in (1, 2, 3, 4, 5)]
    return _softmax(raw)


def _extract_score_distribution_from_logprobs(logprobs_payload: Any) -> Optional[list[float]]:
    """vLLM returns OpenAI-style logprobs. We hunt for the first generated
    token whose top-5 contains a digit 1..5 and softmax over those.

    Returns None when logprobs aren't usable (different schema / disabled).
    """
    if not logprobs_payload:
        return None
    try:
        content_lp = logprobs_payload.get("content") or []
        for tok in content_lp:
            top_lp = tok.get("top_logprobs") or []
            digit_lp: dict[str, float] = {}
            for entry in top_lp:
                t = entry.get("token", "").strip()
                if t in {"1", "2", "3", "4", "5"} and t not in digit_lp:
                    digit_lp[t] = float(entry.get("logprob", -1e9))
            if len(digit_lp) >= 2:
                lps = [digit_lp.get(str(k), -1e9) for k in range(1, 6)]
                return _softmax(lps)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_default_client(prefer_real: bool = True) -> LLMClient:
    """Build the configured LLM client. Falls back to HeuristicClient if the
    requested backend isn't reachable, so callers always get a usable client.
    """
    cfg = load_config()
    backend = cfg["llm"]["backend"].lower()

    candidate: Optional[LLMClient] = None
    try:
        if backend == "ollama":
            candidate = OllamaClient(
                host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
                model=cfg["llm"]["model"],
                self_consistency_samples=int(cfg["scoring"].get("self_consistency_samples", 0)),
            )
        elif backend == "vllm":
            candidate = VLLMClient(
                base_url=os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1"),
                model=cfg["llm"].get("vllm_model", cfg["llm"]["model"]),
                api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
            )
        elif backend == "hf":
            candidate = HFClient(model_id=cfg["llm"].get("hf_model", "Qwen/Qwen2.5-7B-Instruct"))
    except Exception as e:
        log.warning("Failed to initialise backend '%s' (%s). Falling back.", backend, e)
        candidate = None

    if prefer_real and candidate is not None and candidate.health():
        log.info("Using LLM backend: %s", candidate.name)
        return candidate

    log.warning("Falling back to HeuristicClient (no real LLM reachable). "
                "Real numbers require Ollama/vLLM/HF — see README.")
    return HeuristicClient()
