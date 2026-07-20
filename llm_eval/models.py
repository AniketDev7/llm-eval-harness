"""Data models for the eval harness.

Uses pydantic for validation. These models flow through every layer:
YAML -> Suite -> Runner -> Evaluators -> RunRecord -> Storage -> Reporters.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class ModelConfig(BaseModel):
    """Provider-agnostic generation config."""
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1)


class Thresholds(BaseModel):
    """Composite-score thresholds for PASS/REVIEW/ALERT/PAUSE."""
    review: float = Field(default=0.80, ge=0.0, le=1.0)
    alert: float = Field(default=0.70, ge=0.0, le=1.0)
    pause: float = Field(default=0.60, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_order(self) -> "Thresholds":
        if not self.review >= self.alert >= self.pause:
            raise ValueError("thresholds must satisfy review >= alert >= pause")
        return self


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
    type: str = Field(min_length=1)
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
    runs: int = Field(default=1, ge=1)


class EvalSuite(BaseModel):
    """A full suite of eval cases."""
    name: str
    version: str = "1.0"
    providers: list[str] = Field(default_factory=lambda: ["openai"], min_length=1)
    model_config_settings: ModelConfig = Field(default_factory=ModelConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    evals: list[EvalCase] = Field(default_factory=list, min_length=1)


class AssertionResult(BaseModel):
    """The result of evaluating a single assertion."""
    type: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
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
    model_version: str = ""
    completions: list[CompletionResult] = Field(default_factory=list)
    assertions: list[AssertionResult] = Field(default_factory=list)
    error: Optional[str] = None


class RunRecord(BaseModel):
    """A complete run of a suite. Persisted in SQLite."""
    id: str
    timestamp: str
    suite_name: str
    suite_version: str
    provider: str
    composite_score: float = Field(ge=0.0, le=1.0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    accuracy_score: float = Field(ge=0.0, le=1.0)
    format_score: float = Field(ge=0.0, le=1.0)
    hallucination_score: float = Field(ge=0.0, le=1.0)
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
