"""Tests for the weighted composite scorer + thresholds."""
from __future__ import annotations

from llm_eval.models import AssertionResult, EvalResult, Thresholds
from llm_eval.scorer.scorer import score_run, evaluate_threshold


def _result(name: str, assertions: list[AssertionResult]) -> EvalResult:
    return EvalResult(
        eval_name=name, category="format", provider="mock",
        prompt="p", response="r", latency_ms=10, tokens_used=0,
        assertions=assertions,
    )


def test_all_passing_yields_high_composite():
    results = [
        _result("a", [AssertionResult(type="json_schema", passed=True, score=1.0)]),
        _result("b", [AssertionResult(type="semantic_similarity", passed=True, score=1.0)]),
        _result("c", [AssertionResult(type="faithfulness", passed=True, score=1.0)]),
    ]
    scores = score_run(results)
    assert scores["composite"] >= 0.99
    assert scores["coverage"] == 1.0


def test_all_format_failing_drops_format_score():
    results = [
        _result("a", [AssertionResult(type="json_schema", passed=False, score=0.0)]),
        _result("b", [AssertionResult(type="semantic_similarity", passed=True, score=1.0)]),
    ]
    scores = score_run(results)
    assert scores["format"] == 0.0
    # composite = 0.4 * 0.5 (only b passes) + 0.3 * 1.0 + 0.2 * 0.0 + 0.1 * 1.0 = 0.6
    assert abs(scores["composite"] - 0.6) < 0.01


def test_threshold_pass():
    assert evaluate_threshold(0.95, Thresholds()) == "PASS"


def test_threshold_review():
    assert evaluate_threshold(0.75, Thresholds()) == "REVIEW"


def test_threshold_alert():
    assert evaluate_threshold(0.65, Thresholds()) == "ALERT"


def test_threshold_pause():
    assert evaluate_threshold(0.50, Thresholds()) == "PAUSE"


def test_empty_results_returns_zero():
    scores = score_run([])
    assert scores["composite"] == 0.0
    assert scores["coverage"] == 0.0


def test_coverage_partial():
    results = [
        _result("a", [AssertionResult(type="json_schema", passed=True, score=1.0)]),
        _result("b", [AssertionResult(type="json_schema", passed=False, score=0.0)]),
    ]
    scores = score_run(results)
    assert scores["coverage"] == 0.5


def test_provider_error_forces_zero_score():
    result = _result("error", [])
    result.error = "provider unavailable"
    assert score_run([result]) == {
        "composite": 0.0,
        "coverage": 0.0,
        "accuracy": 0.0,
        "format": 0.0,
        "hallucination": 0.0,
    }
