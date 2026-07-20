"""Tests for release risk and assertion-level regression reports."""
from llm_eval.models import AssertionResult, EvalResult, RunRecord
from llm_eval.quality import assess_risk, compare_run_records


def run_record(run_id: str, assertions: list[AssertionResult], score: float = 0.8) -> RunRecord:
    return RunRecord(
        id=run_id,
        timestamp="2026-01-01T00:00:00Z",
        suite_name="suite",
        suite_version="1",
        provider="mock",
        composite_score=score,
        coverage_score=score,
        accuracy_score=score,
        format_score=score,
        hallucination_score=score,
        threshold_status="PASS",
        results=[EvalResult(
            eval_name="case",
            category="edge_case",
            provider="mock",
            prompt="prompt",
            response="response",
            latency_ms=1,
            tokens_used=1,
            assertions=assertions,
        )],
    )


def assertion(kind: str, passed: bool, score: float) -> AssertionResult:
    return AssertionResult(type=kind, passed=passed, score=score, detail="detail")


def test_risk_weights_security_failures_more_heavily():
    record = run_record("risk", [
        assertion("max_length", False, 0.0),
        assertion("prompt_injection_resistance", False, 0.0),
        assertion("json_schema", True, 1.0),
    ])
    report = assess_risk(record)
    assert report.failed_checks == 2
    assert report.score > 50
    assert {finding.severity for finding in report.findings} == {"low", "critical"}


def test_regression_finds_new_failure_degradation_and_missing_check():
    baseline = run_record("base", [
        assertion("no_pii", True, 1.0),
        assertion("semantic_similarity", True, 0.9),
        assertion("max_length", True, 1.0),
    ], score=0.95)
    candidate = run_record("candidate", [
        assertion("no_pii", False, 0.0),
        assertion("semantic_similarity", True, 0.7),
    ], score=0.70)
    report = compare_run_records(baseline, candidate)
    assert report.has_regressions
    assert len(report.newly_failed) == 1
    assert len(report.degraded) == 1
    assert report.missing_checks == ["case/max_length[0]"]
    assert report.composite_delta == -0.25


def test_regression_rejects_different_suites():
    baseline = run_record("base", [])
    candidate = run_record("candidate", [])
    candidate.suite_name = "other"
    try:
        compare_run_records(baseline, candidate)
    except ValueError as exc:
        assert "same suite" in str(exc)
    else:
        raise AssertionError("expected suite mismatch")
