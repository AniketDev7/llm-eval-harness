"""Operational evaluators: latency, cost, etc."""
from __future__ import annotations

from llm_eval.models import Assertion, AssertionResult, CompletionResult


def eval_max_latency(assertion: Assertion, result: CompletionResult, context: dict) -> AssertionResult:
    limit = int(assertion.params.get("value", 10000))
    passed = result.latency_ms <= limit
    return AssertionResult(
        type=assertion.type, passed=passed, score=1.0 if passed else 0.0,
        detail=f"Latency {result.latency_ms}ms {'<=' if passed else '>'} max {limit}ms",
    )
