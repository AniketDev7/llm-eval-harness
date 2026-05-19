"""Data models for the eval harness.

Uses pydantic for validation. These models flow through every layer:
YAML -> Suite -> Runner -> Evaluators -> RunRecord -> Storage -> Reporters.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Provider-agnostic generation config."""
    temperature: float = 0.1
    max_tokens: int = 1000


class Thresholds(BaseModel):
    """Composite-score thresholds for PASS/REVIEW/ALERT/PAUSE."""
    review: float = 0.80
    alert: float = 0.70
    pause: float = 0.60


class CompletionResult(BaseModel):
    """The result of a single LLM call."""
    text: str
    latency_ms: int
    tokens_used: int = 0
    model_version: str = ""
    error: Optional[str] = None


class Assertion(BaseModel):
    """A single assertion attached to an eval case.

    `type` selects the evaluator; all other fields are evaluator-specific
    and stored in `params`.
    """
    type: str
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @classmethod
    def from_dict(cls, data: dict) -> "Assertion":
        atype = data.get("type")
        params = {k: v for k, v in data.items() if k != "type"}
        return cls(type=atype, params=params)


class EvalCase(BaseModel):
    """A single eval case loaded from YAML."""
    name: str
    category: str
    prompt: str
    variables: dict[str, Any] = Field(default_factory=dict)
    assertions: list[Assertion] = Field(default_factory=list)
    runs: int = 1


class EvalSuite(BaseModel):
    """A full suite of eval cases."""
    name: str
    version: str = "1.0"
    providers: list[str] = Field(default_factory=lambda: ["openai"])
    model_config_settings: ModelConfig = Field(default_factory=ModelConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    evals: list[EvalCase] = Field(default_factory=list)


class AssertionResult(BaseModel):
    """The result of evaluating a single assertion."""
    type: str
    passed: bool
    score: float
    detail: str = ""


class EvalResult(BaseModel):
    """The result of running one eval case against one provider."""
    eval_name: str
    category: str
    provider: str
    prompt: str
    response: str
    latency_ms: int
    tokens_used: int
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: Optional[str] = None


class RunRecord(BaseModel):
    """A complete run of a suite. Persisted in SQLite."""
    id: str
    timestamp: str
    suite_name: str
    suite_version: str
    provider: str
    composite_score: float
    coverage_score: float
    accuracy_score: float
    format_score: float
    hallucination_score: float
    threshold_status: str
    results: list[EvalResult] = Field(default_factory=list)


class DriftReport(BaseModel):
    """Drift detection result for a suite/provider."""
    suite_name: str
    provider: str
    baseline_score: Optional[float] = None
    recent_scores: list[float] = Field(default_factory=list)
    trend: str = "stable"  # stable | improving | degrading
    alert: bool = False
    message: str = ""
