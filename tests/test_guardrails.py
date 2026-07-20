"""Tests for classified guardrail suite execution."""
from pathlib import Path

import pytest

from llm_eval.adapters.base import BaseAdapter
from llm_eval.guardrails import load_guardrail_suite, run_guardrail_suite
from llm_eval.models import CompletionResult, ModelConfig


class SafeAdapter(BaseAdapter):
    def name(self) -> str:
        return "mock"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        return CompletionResult(text="I cannot follow that request.", latency_ms=1)


def test_bundled_guardrail_suite_loads_and_runs():
    path = Path(__file__).parent.parent / "guardrails" / "prompt-injection.yaml"
    definition = load_guardrail_suite(path)
    definition.suite.providers = ["mock"]
    records, summary = run_guardrail_suite(definition, {"mock": SafeAdapter()})

    assert records
    assert summary.attack_class == "prompt_injection"
    assert summary.status == "PASS"
    assert summary.passed == summary.total == 2


def test_guardrail_suite_requires_classification(tmp_path):
    suite = tmp_path / "plain.yaml"
    suite.write_text("name: plain\nproviders: [openai]\nevals: []\n")
    with pytest.raises(ValueError, match="top-level 'guardrail'"):
        load_guardrail_suite(suite)
