"""Drift detection: compares a run's composite score to its baseline and recent history."""
from __future__ import annotations

from typing import Optional

from llm_eval.models import DriftReport, RunRecord
from llm_eval.storage.db import get_baseline, list_runs, save_baseline


DEGRADATION_PCT = 0.10  # 10% drop relative to baseline triggers an alert.


def capture_baseline(record: RunRecord) -> None:
    """Persist this run's scores as the new baseline for its suite/provider."""
    save_baseline(record)


def check_drift(suite_name: str, provider: str, window: int = 8) -> DriftReport:
    """Compare baseline vs recent runs to detect score degradation.

    `window` is the number of most-recent runs to inspect.
    """
    baseline = get_baseline(suite_name, provider)
    runs = list_runs(limit=window, suite_name=suite_name, provider=provider)

    recent_scores = [float(r["composite_score"]) for r in runs]

    if baseline is None:
        return DriftReport(
            suite_name=suite_name, provider=provider,
            recent_scores=recent_scores,
            trend="stable",
            alert=False,
            message="No baseline captured yet. Run `llm-eval baseline save`.",
        )

    baseline_score = float(baseline["composite_score"])

    # Trend: compare first half vs second half of recent runs.
    trend = "stable"
    if len(recent_scores) >= 4:
        half = len(recent_scores) // 2
        # recent_scores is DESC by timestamp -> earlier indexes = newer.
        newer_avg = sum(recent_scores[:half]) / half
        older_avg = sum(recent_scores[half:]) / (len(recent_scores) - half)
        if newer_avg > older_avg + 0.02:
            trend = "improving"
        elif newer_avg < older_avg - 0.02:
            trend = "degrading"

    alert = False
    message = "Stable vs baseline."
    if recent_scores:
        latest = recent_scores[0]
        drop = baseline_score - latest
        if baseline_score > 0 and (drop / baseline_score) >= DEGRADATION_PCT:
            alert = True
            message = (
                f"Latest composite {latest:.3f} is {drop / baseline_score * 100:.1f}% "
                f"below baseline {baseline_score:.3f}."
            )

    return DriftReport(
        suite_name=suite_name, provider=provider,
        baseline_score=baseline_score,
        recent_scores=recent_scores,
        trend=trend,
        alert=alert,
        message=message,
    )
