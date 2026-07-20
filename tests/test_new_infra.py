"""Tests for per-model baselines, worker/budget runner, and executor helpers."""
from pathlib import Path

import pytest

from llm_eval.adapters.base import BaseAdapter
from llm_eval.mcp_support import classify_skip_reason, load_mcp_scenario, run_mcp_scenario
from llm_eval.mcp_support.executor import _cap_payload
from llm_eval.models import CompletionResult, EvalCase, EvalSuite, ModelConfig
from llm_eval.runner.runner import Runner
from llm_eval.storage.db import get_baseline, save_baseline, save_run


SUITES = Path(__file__).parent.parent / "examples" / "vulnerable_workspace_mcp" / "suites"


class FakeAdapter(BaseAdapter):
    """Deterministic adapter that reports a fixed token cost per call."""

    def __init__(self, model="fake-model", tokens=1000):
        self.model = model
        self.tokens = tokens
        self.calls = 0

    def name(self):
        return "fake"

    def complete(self, prompt, config):
        self.calls += 1
        return CompletionResult(
            text="ok", latency_ms=1, tokens_used=self.tokens, model_version=self.model,
        )


def _suite(n_cases: int) -> EvalSuite:
    return EvalSuite(
        name="s", version="1", providers=["fake"],
        model_config_settings=ModelConfig(),
        evals=[EvalCase(name=f"c{i}", category="format", prompt="p",
                        assertions=[]) for i in range(n_cases)],
    )


# ---- per-(provider, model) baseline keying ----

def _record(monkeypatch_provider="fake", model="m1", score=0.9):
    from llm_eval.models import RunRecord
    return RunRecord(
        id=f"id-{model}", timestamp="2026-01-01T00:00:00Z",
        suite_name="suite", suite_version="1", provider="anthropic", model=model,
        composite_score=score, coverage_score=score, accuracy_score=score,
        format_score=score, hallucination_score=score, threshold_status="PASS",
    )


def test_baseline_keyed_by_model(tmp_path):
    db = str(tmp_path / "b.db")
    save_baseline(_record(model="haiku", score=0.90), path=db)
    save_baseline(_record(model="opus", score=0.70), path=db)

    haiku = get_baseline("suite", "anthropic", "haiku", path=db)
    opus = get_baseline("suite", "anthropic", "opus", path=db)
    assert haiku["composite_score"] == 0.90
    assert opus["composite_score"] == 0.70
    # Without a model filter, most-recent regardless of model is returned.
    assert get_baseline("suite", "anthropic", path=db) is not None


def test_run_persists_model(tmp_path):
    db = str(tmp_path / "r.db")
    suite = _suite(1)
    rec = Runner(suite, adapters={"fake": FakeAdapter(model="fake-v2")}).run()[0]
    assert rec.model == "fake-v2"
    save_run(rec, path=db)  # should not raise with the new model column


# ---- worker pool + budget guard ----

def test_workers_run_all_cases():
    adapter = FakeAdapter()
    rec = Runner(_suite(5), adapters={"fake": adapter}, workers=3).run()[0]
    assert len(rec.results) == 5
    assert adapter.calls == 5


def test_budget_stops_launching_cases():
    # Each call ~ estimate_cost(fake, 1000). Set a cap that only allows a couple.
    adapter = FakeAdapter(tokens=1_000_000)  # ~ dollars per call
    runner = Runner(_suite(10), adapters={"fake": adapter}, max_usd=6.0)
    rec = runner.run()[0]
    assert len(rec.results) < 10
    assert runner.guard.blocked() > 0
    assert runner.guard.exceeded()


# ---- executor helpers ----

def test_cap_payload_truncates(monkeypatch):
    monkeypatch.setenv("LLM_EVAL_TOOL_RESULT_CAP", "50")
    big = {"ok": True, "data": "x" * 500}
    capped = _cap_payload(big)
    assert capped.get("_truncated") is True
    assert capped["_original_chars"] > 50


def test_classify_skip_reason():
    assert classify_skip_reason({"reason": "tool not advertised by server"})
    assert classify_skip_reason({"reason": "no stack configured"})
    assert classify_skip_reason({"reason": "tenant access denied"}) is None


# ---- phased (setup/teardown) execution ----

@pytest.mark.asyncio
async def test_self_cleaning_write_scenario_grades_only_main_calls():
    scenario = load_mcp_scenario(SUITES / "self-cleaning-write.yaml")
    assert scenario.setup and scenario.teardown
    record = await run_mcp_scenario(scenario)
    result = record.results[0]
    assert all(a.passed for a in result.assertions)
    # Setup and teardown ran but are not counted as graded tool calls.
    completion = result.completions[0]
    assert len(completion.tool_calls) == 1
    kinds = {step.kind for step in completion.trajectory}
    assert "setup_call" in kinds and "teardown_call" in kinds


@pytest.mark.asyncio
async def test_nonexistent_grounding_blocks_and_leaks_nothing():
    scenario = load_mcp_scenario(SUITES / "nonexistent-grounding.yaml")
    record = await run_mcp_scenario(scenario)
    assert all(a.passed for a in record.results[0].assertions)
