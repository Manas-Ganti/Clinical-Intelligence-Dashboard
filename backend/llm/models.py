"""Which models the Ask layer can run on, and where each one is served from.

Two providers, one tool surface:

  * **anthropic** — Claude, via the Anthropic SDK (`ANTHROPIC_API_KEY`).
  * **vtarc**     — the open models Virginia Tech ARC hosts, via their
                    OpenAI-compatible endpoint at
                    ``https://llm-api.arc.vt.edu/api/v1`` (`VTARC_API_KEY`,
                    minted at llm.arc.vt.edu → Settings → Account → API keys).

The registry exists because the ARC catalogue ships the *same* weights under
several ids that differ only in how hard the model is allowed to think
(`reasoning_effort`, or `enable_thinking: false` for the non-thinking variants).
Those are request parameters, not separate endpoints, so the id alone is not
enough to call one correctly — the spec carries the parameters with it.

That mapping is the point of the eval harness next door: the tool-calling
surface is fixed, so `python evals/run_eval.py --model <id>` turns "which model
can drive this dashboard, at what thinking budget" into a number.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

import backend.config  # noqa: F401  — imported for its load_dotenv() side effect

logger = structlog.get_logger()

ANTHROPIC = "anthropic"
VTARC = "vtarc"

# ARC's OpenAI-compatible base. Overridable so this still works if ARC moves the
# route, or against any other OpenAI-compatible server (vLLM, Ollama, LM Studio).
VTARC_BASE_URL_DEFAULT = "https://llm-api.arc.vt.edu/api/v1"

FALLBACK_MODEL = "claude-opus-4-8"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    max_context: int
    # Sent with every request: reasoning_effort, enable_thinking, … These are
    # not OpenAI-standard, so they ride in extra_body rather than as kwargs.
    params: dict = field(default_factory=dict)

    @property
    def credential_env(self) -> str:
        return "ANTHROPIC_API_KEY" if self.provider is ANTHROPIC else "VTARC_API_KEY"


def _vtarc(model_id: str, max_context: int, **params: object) -> ModelSpec:
    return ModelSpec(id=model_id, provider=VTARC, max_context=max_context, params=params)


_128K = 128_000
_512K = 512_000

MODELS: dict[str, ModelSpec] = {
    # -- Anthropic ---------------------------------------------------------- #
    "claude-opus-4-8": ModelSpec("claude-opus-4-8", ANTHROPIC, 200_000),
    "claude-sonnet-5": ModelSpec("claude-sonnet-5", ANTHROPIC, 200_000),
    "claude-haiku-4-5-20251001": ModelSpec("claude-haiku-4-5-20251001", ANTHROPIC, 200_000),
    # -- VT ARC (llm-api.arc.vt.edu) ---------------------------------------- #
    "gpt-oss-120b": _vtarc("gpt-oss-120b", _128K, reasoning_effort="medium"),
    "gpt-oss-120b-thinking-low": _vtarc("gpt-oss-120b-thinking-low", _128K, reasoning_effort="low"),
    "gpt-oss-120b-thinking-high": _vtarc("gpt-oss-120b-thinking-high", _128K, reasoning_effort="high"),
    "GLM-5.2": _vtarc("GLM-5.2", _128K, reasoning_effort="max"),
    "GLM-5.2-thinking-high": _vtarc("GLM-5.2-thinking-high", _128K, reasoning_effort="high"),
    "GLM-5.2-non-thinking": _vtarc("GLM-5.2-non-thinking", _128K, enable_thinking=False),
    "Kimi-K3": _vtarc("Kimi-K3", _128K, reasoning_effort="max"),
    "Kimi-K3-thinking-low": _vtarc("Kimi-K3-thinking-low", _128K, reasoning_effort="low"),
    "Kimi-K3-thinking-high": _vtarc("Kimi-K3-thinking-high", _128K, reasoning_effort="high"),
    "DeepSeek-V4-Flash": _vtarc("DeepSeek-V4-Flash", _512K, reasoning_effort="high"),
    "DeepSeek-V4-Flash-thinking-low": _vtarc("DeepSeek-V4-Flash-thinking-low", _512K, reasoning_effort="low"),
    "DeepSeek-V4-Flash-thinking-max": _vtarc("DeepSeek-V4-Flash-thinking-max", _512K, reasoning_effort="max"),
}


def resolve(model_id: str) -> ModelSpec:
    """Look up a model id, tolerating ids the registry has not caught up with.

    ARC adds and retires models faster than this file changes, so an unknown id
    is not an error — it is routed by prefix and sent with no extra parameters.
    The registry's job is to carry the *parameters*, not to gatekeep the catalogue.
    """
    spec = MODELS.get(model_id)
    if spec is not None:
        return spec

    provider = ANTHROPIC if model_id.startswith("claude") else VTARC
    logger.warning("llm_model_not_in_registry", model=model_id, assumed_provider=provider)
    return ModelSpec(id=model_id, provider=provider, max_context=_128K)


def default_model() -> str:
    """The model a bare `QueryEngine(db)` runs on: `LLM_MODEL`, else Claude.

    Read at call time, not import time, so tests and a `.env` edit both take
    effect without reimporting the module.
    """
    return os.getenv("LLM_MODEL") or FALLBACK_MODEL


def vtarc_base_url() -> str:
    return os.getenv("VTARC_BASE_URL") or VTARC_BASE_URL_DEFAULT


def missing_credential(spec: ModelSpec) -> str | None:
    """The env var this model needs and does not have, or None if it is set."""
    return None if os.getenv(spec.credential_env) else spec.credential_env
