"""Assertion-level comparison between a known baseline and candidate run."""
from __future__ import annotations

from pydantic import BaseModel, Field

from llm_eval.models import AssertionResult, RunRecord


class RegressionFinding(BaseModel):
    eval_name: str
    assertion_type: str
    kind: str
    baseline_score: float
    candidate_score: float


class RegressionReport(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    composite_delta: float
    newly_failed: list[RegressionFinding] = Field(default_factory=list)
    degraded: list[RegressionFinding] = Field(default_factory=list)
    resolved: list[RegressionFinding] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        return bool(self.newly_failed or self.degraded or self.missing_checks)


def _index(record: RunRecord) -> dict[tuple[str, str, int], AssertionResult]:
    indexed: dict[tuple[str, str, int], AssertionResult] = {}
    for result in record.results:
        occurrences: dict[str, int] = {}
        for assertion in result.assertions:
            occurrence = occurrences.get(assertion.type, 0)
            occurrences[assertion.type] = occurrence + 1
            indexed[(result.eval_name, assertion.type, occurrence)] = assertion
    return indexed


def compare_run_records(
    baseline: RunRecord,
    candidate: RunRecord,
    tolerance: float = 0.05,
) -> RegressionReport:
    if baseline.suite_name != candidate.suite_name:
        raise ValueError("baseline and candidate must belong to the same suite")
    baseline_items = _index(baseline)
    candidate_items = _index(candidate)
    newly_failed: list[RegressionFinding] = []
    degraded: list[RegressionFinding] = []
    resolved: list[RegressionFinding] = []

    for key, before in baseline_items.items():
        after = candidate_items.get(key)
        if after is None:
            continue
        finding = RegressionFinding(
            eval_name=key[0],
            assertion_type=key[1],
            kind="",
            baseline_score=before.score,
            candidate_score=after.score,
        )
        if before.passed and not after.passed:
            newly_failed.append(finding.model_copy(update={"kind": "new_failure"}))
        elif not before.passed and after.passed:
            resolved.append(finding.model_copy(update={"kind": "resolved"}))
        elif before.passed and after.passed and before.score - after.score >= tolerance:
            degraded.append(finding.model_copy(update={"kind": "score_degradation"}))

    missing = [
        f"{eval_name}/{assertion_type}[{occurrence}]"
        for eval_name, assertion_type, occurrence in baseline_items.keys() - candidate_items.keys()
    ]
    return RegressionReport(
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        composite_delta=round(candidate.composite_score - baseline.composite_score, 4),
        newly_failed=newly_failed,
        degraded=degraded,
        resolved=resolved,
        missing_checks=sorted(missing),
    )
