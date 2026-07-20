"""A raw single-shot LLM completion primitive for scorers.

`judge_complete` is deliberately minimal: one call, no retries beyond the
adapter's own, and it never raises — failures come back as ``error`` on the
result. RAGAS-style faithfulness and DeepEval-style task completion
(see :mod:`llm_eval.metrics`) are built on top of it by injection, which keeps
those scorers pure and unit-testable without a live provider.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Optional

from llm_eval.models import CompletionResult, ModelConfig


JudgeFn = Callable[[str, str], CompletionResult]


def default_provider() -> Optional[str]:
    """Cheapest available judge provider, or None if no key is configured."""
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def judge_complete(
    system: str,
    user: str,
    *,
    provider: Optional[str] = None,
    max_tokens: int = 512,
) -> CompletionResult:
    """Run a single completion on a cheap judge model. Never raises.

    Returns a CompletionResult whose ``error`` is set on any failure (including
    "no API key"), so callers can skip rather than crash.
    """
    provider = provider or default_provider()
    if provider is None:
        return CompletionResult(
            text="", latency_ms=0, model_version="",
            error="no API key configured for judge",
        )
    prompt = f"{system}\n\n{user}" if system else user
    try:
        from llm_eval.adapters import get_adapter

        adapter = get_adapter(provider)
        return adapter.complete(prompt, ModelConfig(temperature=0.0, max_tokens=max_tokens))
    except Exception as exc:  # noqa: BLE001
        return CompletionResult(
            text="", latency_ms=0, model_version="",
            error=f"{exc.__class__.__name__}: {exc}",
        )


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from a model reply.

    Handles ```json fences and locates the first balanced object/array. Returns
    None when nothing parseable is found.
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except (TypeError, json.JSONDecodeError):
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except (TypeError, json.JSONDecodeError):
                continue
    return None
