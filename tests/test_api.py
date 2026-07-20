"""API contract tests for complete suite execution."""
from fastapi.testclient import TestClient

from llm_eval.adapters.base import BaseAdapter
from llm_eval.api.main import app
from llm_eval.models import CompletionResult, ModelConfig


class ApiAdapter(BaseAdapter):
    def name(self) -> str:
        return "mock"

    def complete(self, prompt: str, config: ModelConfig) -> CompletionResult:
        return CompletionResult(text="hello", latency_ms=1, model_version="api-test")


def test_run_suite_executes_original_assertions(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_EVAL_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr("llm_eval.runner.runner.get_adapter", lambda name, model=None: ApiAdapter())
    yaml_text = """
name: api-suite
providers: [mock]
model_config: {temperature: 0.0, max_tokens: 10}
thresholds: {review: 0.8, alert: 0.7, pause: 0.6}
evals:
  - name: exact-case
    category: format
    prompt: "Say hello to {name}"
    variables: {name: Ada}
    assertions:
      - type: regex
        pattern: hello
"""
    response = TestClient(app).post("/api/run-suite", json={"yaml_text": yaml_text})
    assert response.status_code == 200
    result = response.json()["runs"][0]["results"][0]
    assert result["prompt"] == "Say hello to Ada"
    assert result["assertions"][0]["type"] == "regex"
    assert result["assertions"][0]["passed"] is True


def test_run_suite_rejects_invalid_yaml():
    response = TestClient(app).post("/api/run-suite", json={"yaml_text": "- not-a-suite"})
    assert response.status_code == 422
