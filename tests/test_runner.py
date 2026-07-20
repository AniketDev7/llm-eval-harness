"""Integration test for the runner using a mock adapter."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from llm_eval.adapters.base import BaseAdapter
from llm_eval.models import AgentStep, CompletionResult, ModelConfig, RunRecord, ToolCall
from llm_eval.runner.runner import Runner, load_suite, load_suite_text
from llm_eval.storage.db import get_audit_results_for_run, save_run, list_runs, init_db


class MockAdapter(BaseAdapter):
    """Returns canned responses, useful for offline runner tests."""

    def __init__(self, text: str = '{"name": "test", "score": 100}') -> None:
        self.text = text

    def name(self) -> str:
        return "mock"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        return CompletionResult(
            text=self.text, latency_ms=50, tokens_used=10, model_version="mock-v1",
        )


class ErrorAdapter(BaseAdapter):
    def name(self) -> str:
        return "error"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        return CompletionResult(text="", latency_ms=1, error="provider unavailable")


class AgentAdapter(BaseAdapter):
    def name(self) -> str:
        return "agent"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        return CompletionResult(
            text="Looked it up.", latency_ms=2, model_version="agent-v1",
            tool_calls=[ToolCall(name="lookup", arguments={"id": "42"})],
            trajectory=[
                AgentStep(kind="tool_call", name="lookup", success=True),
                AgentStep(kind="final", content="Looked it up."),
            ],
        )


YAML_SUITE = """
name: test-suite
version: "1.0"
providers: [mock]

model_config:
  temperature: 0.0
  max_tokens: 100

thresholds:
  review: 0.80
  alert: 0.70
  pause: 0.60

evals:
  - name: json_test
    category: format
    prompt: "Return JSON"
    assertions:
      - type: json_schema
        schema:
          type: object
          required: [name, score]
  - name: length_test
    category: format
    prompt: "Short response"
    assertions:
      - type: max_length
        value: 1000
      - type: min_length
        value: 1
"""


@pytest.fixture()
def yaml_path(tmp_path: Path) -> Path:
    p = tmp_path / "suite.yaml"
    p.write_text(YAML_SUITE)
    return p


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("LLM_EVAL_DB_PATH", str(db_path))
    return db_path


def test_load_suite_parses_yaml(yaml_path):
    suite = load_suite(yaml_path)
    assert suite.name == "test-suite"
    assert suite.providers == ["mock"]
    assert len(suite.evals) == 2
    assert suite.evals[0].assertions[0].type == "json_schema"


def test_load_suite_text_preserves_full_suite_semantics():
    suite = load_suite_text(YAML_SUITE)
    assert suite.providers == ["mock"]
    assert suite.model_config_settings.max_tokens == 100
    assert suite.thresholds.review == 0.8
    assert len(suite.evals) == 2
    assert len(suite.evals[1].assertions) == 2


def test_runner_executes_with_mock_adapter(yaml_path):
    suite = load_suite(yaml_path)
    runner = Runner(suite, adapters={"mock": MockAdapter()})
    records = runner.run()

    assert len(records) == 1
    rec = records[0]
    assert isinstance(rec, RunRecord)
    assert rec.suite_name == "test-suite"
    assert rec.provider == "mock"
    assert len(rec.results) == 2
    assert rec.composite_score > 0
    # Both evals should pass with this canned JSON.
    for r in rec.results:
        for a in r.assertions:
            assert a.passed, f"{r.eval_name}/{a.type} failed: {a.detail}"


def test_runner_persists_to_sqlite(yaml_path, tmp_db):
    suite = load_suite(yaml_path)
    runner = Runner(suite, adapters={"mock": MockAdapter()})
    records = runner.run()
    for r in records:
        save_run(r)

    rows = list_runs(limit=10)
    assert any(row["id"] == records[0].id for row in rows)


def test_runner_handles_failing_assertions():
    """Run with a non-JSON response and verify failure is captured cleanly."""
    yaml = """
name: fail-suite
version: "1.0"
providers: [mock]
model_config: {}
thresholds: {}
evals:
  - name: should_fail
    category: format
    prompt: ""
    assertions:
      - type: json_schema
        schema: {type: object}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml)
        path = f.name
    try:
        suite = load_suite(path)
        runner = Runner(suite, adapters={"mock": MockAdapter(text="this is not json")})
        records = runner.run()
        rec = records[0]
        assert not rec.results[0].assertions[0].passed
        # Status should not be PASS.
        assert rec.threshold_status != "PASS"
    finally:
        os.unlink(path)


def test_variable_substitution(tmp_path):
    yaml = """
name: var-suite
version: "1.0"
providers: [mock]
model_config: {}
thresholds: {}
evals:
  - name: substituted
    category: format
    prompt: "Greet {name}."
    variables:
      name: "Alice"
    assertions:
      - type: min_length
        value: 1
"""
    p = tmp_path / "v.yaml"
    p.write_text(yaml)
    suite = load_suite(p)
    runner = Runner(suite, adapters={"mock": MockAdapter()})
    records = runner.run()
    assert records[0].results[0].prompt == "Greet Alice."


def test_provider_error_can_never_score_pass(yaml_path):
    suite = load_suite(yaml_path)
    suite.providers = ["error"]
    record = Runner(suite, adapters={"error": ErrorAdapter()}).run()[0]

    assert record.composite_score == 0.0
    assert record.threshold_status == "PAUSE"
    assert all(r.error == "provider unavailable" for r in record.results)
    assert all(r.assertions[0].type == "provider_error" for r in record.results)


def test_audit_trail_keeps_model_and_every_completion(tmp_db):
    suite = load_suite(Path(__file__).parent.parent / "evals" / "quickstart.yaml")
    suite.providers = ["mock"]
    suite.evals = [suite.evals[0]]
    suite.evals[0].runs = 3
    record = Runner(suite, adapters={"mock": MockAdapter()}).run()[0]
    save_run(record)

    audit = get_audit_results_for_run(record.id)
    assert len(audit) == 1
    assert audit[0]["model_version"] == "mock-v1"
    assert len(audit[0]["completions"]) == 3


def test_audit_trail_keeps_cases_without_assertions(tmp_db):
    suite = load_suite(Path(__file__).parent.parent / "evals" / "quickstart.yaml")
    suite.providers = ["mock"]
    suite.evals = [suite.evals[0]]
    suite.evals[0].assertions = []
    record = Runner(suite, adapters={"mock": MockAdapter()}).run()[0]
    save_run(record)

    audit = get_audit_results_for_run(record.id)
    assert len(audit) == 1
    assert audit[0]["assertions"] == []


def test_audit_trail_keeps_structured_agent_trace(tmp_db, yaml_path):
    suite = load_suite(yaml_path)
    suite.providers = ["agent"]
    suite.evals = [suite.evals[0]]
    record = Runner(suite, adapters={"agent": AgentAdapter()}).run()[0]
    save_run(record)

    completion_row = get_audit_results_for_run(record.id)[0]["completions"][0]
    assert completion_row["tool_calls"][0]["name"] == "lookup"
    assert completion_row["trajectory"][-1]["kind"] == "final"
