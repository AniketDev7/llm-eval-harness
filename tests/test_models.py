"""Validation tests for public suite configuration models."""
import pytest
from pydantic import ValidationError

from llm_eval.models import EvalCase, EvalSuite, ModelConfig, Thresholds


def test_generation_config_rejects_invalid_values():
    with pytest.raises(ValidationError):
        ModelConfig(temperature=-0.1)
    with pytest.raises(ValidationError):
        ModelConfig(max_tokens=0)


def test_thresholds_require_valid_order():
    with pytest.raises(ValidationError, match="review >= alert >= pause"):
        Thresholds(review=0.6, alert=0.8, pause=0.5)


def test_suite_requires_provider_and_eval():
    case = EvalCase(name="case", category="format", prompt="hello")
    with pytest.raises(ValidationError):
        EvalSuite(name="empty-providers", providers=[], evals=[case])
    with pytest.raises(ValidationError):
        EvalSuite(name="empty-evals", providers=["openai"], evals=[])
