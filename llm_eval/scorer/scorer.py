"""Weighted composite scoring with PASS/REVIEW/ALERT/PAUSE thresholds.

Per the spec:
  composite = 0.4 * coverage + 0.3 * accuracy + 0.2 * format + 0.1 * hallucination
"""
from __future__ import annotations

from typing import Iterable

from llm_eval.evaluators import ASSERTION_CATEGORY
from llm_eval.models import EvalResult, Thresholds


WEIGHT_COVERAGE = 0.40
WEIGHT_ACCURACY = 0.30
WEIGHT_FORMAT = 0.20
WEIGHT_HALLUCINATION = 0.10


def _avg(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 1.0  # No assertions in this bucket -> treated as neutral.
    return sum(values) / len(values)


def score_run(eval_results: list[EvalResult]) -> dict[str, float]:
    """Compute the four sub-scores and the composite."""
    # Coverage: fraction of eval cases with at least one passing assertion.
    if not eval_results:
        return {"composite": 0.0, "coverage": 0.0, "accuracy": 0.0,
                "format": 0.0, "hallucination": 0.0}

    cases_with_pass = sum(
        1 for r in eval_results
        if any(a.passed for a in r.assertions)
    )
    coverage = cases_with_pass / len(eval_results)

    accuracy_scores: list[float] = []
    format_scores: list[float] = []
    hallucination_scores: list[float] = []

    for r in eval_results:
        for a in r.assertions:
            bucket = ASSERTION_CATEGORY.get(a.type, "accuracy")
            if bucket == "accuracy":
                accuracy_scores.append(a.score)
            elif bucket == "format":
                format_scores.append(a.score)
            elif bucket == "hallucination":
                hallucination_scores.append(a.score)

    accuracy = _avg(accuracy_scores)
    fmt = _avg(format_scores)
    hallucination = _avg(hallucination_scores)

    composite = (
        WEIGHT_COVERAGE * coverage
        + WEIGHT_ACCURACY * accuracy
        + WEIGHT_FORMAT * fmt
        + WEIGHT_HALLUCINATION * hallucination
    )

    return {
        "composite": round(composite, 4),
        "coverage": round(coverage, 4),
        "accuracy": round(accuracy, 4),
        "format": round(fmt, 4),
        "hallucination": round(hallucination, 4),
    }


def evaluate_threshold(score: float, thresholds: Thresholds) -> str:
    """Map a composite score to a threshold status string."""
    if score >= thresholds.review:
        return "PASS"
    if score >= thresholds.alert:
        return "REVIEW"
    if score >= thresholds.pause:
        return "ALERT"
    return "PAUSE"
