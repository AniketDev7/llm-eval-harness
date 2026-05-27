"""Tests for the LLM provider adapters using mock SDK clients."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_eval.adapters.openai_adapter import OpenAIAdapter
from llm_eval.adapters.anthropic_adapter import AnthropicAdapter
from llm_eval.models import ModelConfig


@pytest.fixture()
def model_config():
    return ModelConfig(temperature=0.1, max_tokens=100)


def _make_openai_response(text: str = "hello world", model: str = "gpt-4o-mini"):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage = MagicMock(total_tokens=42)
    return response


def _make_anthropic_response(text: str = "hi there", model: str = "claude-3-5-haiku-latest"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.model = model
    resp.usage = MagicMock(input_tokens=10, output_tokens=12)
    return resp


def test_openai_returns_completion_result(model_config):
    adapter = OpenAIAdapter()
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_openai_response()
    adapter._client = mock_client

    out = adapter.complete("hi", model_config)

    assert out.error is None
    assert out.text == "hello world"
    assert out.tokens_used == 42
    assert out.latency_ms >= 0
    assert "gpt" in out.model_version


def test_openai_handles_errors_gracefully(model_config):
    adapter = OpenAIAdapter()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("boom")
    adapter._client = mock_client

    out = adapter.complete("hi", model_config)

    assert out.error is not None
    assert "boom" in out.error
    assert out.text == ""


def test_anthropic_returns_completion_result(model_config):
    adapter = AnthropicAdapter()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_anthropic_response()
    adapter._client = mock_client

    out = adapter.complete("hi", model_config)

    assert out.error is None
    assert out.text == "hi there"
    assert out.tokens_used == 22
    assert out.latency_ms >= 0


def test_anthropic_handles_errors_gracefully(model_config):
    adapter = AnthropicAdapter()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("nope")
    adapter._client = mock_client

    out = adapter.complete("hi", model_config)

    assert out.error is not None
    assert out.text == ""


def test_adapter_names():
    assert OpenAIAdapter().name() == "openai"
    assert AnthropicAdapter().name() == "anthropic"
